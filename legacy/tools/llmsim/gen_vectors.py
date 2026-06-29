"""
Generate test vectors for dot_int4_tile verification.
Output: SystemVerilog include file with packed test data + expected results.
"""

import random
import sys
from dataclasses import dataclass
from typing import List, Tuple

from .golden import TileConfig, dot_tile, rand_int4, rand_int8

LANES = 128
TILE_O = 32
LANES_PER_O = LANES // TILE_O  # 4


def pack_activation(a_slice: List[int]) -> int:
    """Pack LANES_PER_O int8 activations into one 32-bit word.
    Layout: {a[3], a[2], a[1], a[0]}  (MSB = last lane)
    """
    val = 0
    for l in range(LANES_PER_O):
        ival = a_slice[l] & 0xFF
        val |= ival << (l * 8)
    return val


def pack_weights(w_slice: List[List[int]]) -> List[int]:
    """Pack TILE_O × LANES_PER_O int4 weights into TILE_O 32-bit words.
    Each word encodes 8 int4 weights (only 4 used per word, 16 bits).
    Layout per word: {w[l*4+:4] ...} packed into bits.
    Returns TILE_O words of 32 bits each.
    But the RTL reads a flat 512-bit vector: LANES*4 bits.
    Layout: {ch31_l3, ch31_l2, ch31_l1, ch31_l0, ..., ch0_l3, ch0_l2, ch0_l1, ch0_l0}
    Each 4-bit nibble = signed int4.
    """
    # Build flat bit vector: 128 lanes × 4 bits = 512 bits
    # Use Python int (unlimited precision)
    val = 0
    for o in range(TILE_O):
        for l in range(LANES_PER_O):
            lane_idx = o * LANES_PER_O + l
            ival = w_slice[o][l] & 0xF
            val |= ival << (lane_idx * 4)
    return val  # 512-bit value


def pack_outputs(expected: List[int]) -> int:
    """Pack TILE_O int32 results into 1024-bit value.
    Layout: {y[31], y[30], ..., y[0]} each 32 bits.
    """
    val = 0
    for o in range(TILE_O):
        ival = expected[o] & 0xFFFFFFFF
        val |= ival << (o * 32)
    return val


@dataclass
class TestVector:
    name: str
    tile_k: int
    num_cycles: int
    # Per-cycle inputs
    a_cycles: List[int]    # list of 32-bit packed activations per cycle
    w_cycles: List[int]    # list of 512-bit packed weights per cycle
    expected: int          # 1024-bit packed output


def gen_deterministic() -> List[TestVector]:
    """Generate hand-calculable deterministic test vectors."""
    cfg = TileConfig(lanes=LANES, tile_o=TILE_O)
    vectors = []

    # --- All zeros ---
    a = [0] * LANES_PER_O
    w = [[0] * LANES_PER_O for _ in range(TILE_O)]
    expected = dot_tile(cfg, a, w, tile_k=LANES_PER_O)
    vectors.append(TestVector(
        name="all_zero",
        tile_k=LANES_PER_O,
        num_cycles=1,
        a_cycles=[pack_activation(a)],
        w_cycles=[pack_weights(w)],
        expected=pack_outputs(expected),
    ))

    # --- All ones ---
    a = [1] * LANES_PER_O
    w = [[1] * LANES_PER_O for _ in range(TILE_O)]
    expected = dot_tile(cfg, a, w, tile_k=LANES_PER_O)
    vectors.append(TestVector(
        name="all_one",
        tile_k=LANES_PER_O,
        num_cycles=1,
        a_cycles=[pack_activation(a)],
        w_cycles=[pack_weights(w)],
        expected=pack_outputs(expected),
    ))

    # --- Distinct per-lane (catches lane order bugs) ---
    # Activations: [0, 1, 2, 3]
    # Weights per ch: each channel uses same pattern shifted
    a = list(range(LANES_PER_O))
    w = []
    for o in range(TILE_O):
        # Each channel: [o%8-3, (o+1)%8-3, (o+2)%8-3, (o+3)%8-3] int4
        w_row = [((o + l) % 8) - 3 for l in range(LANES_PER_O)]
        w.append(w_row)
    expected = dot_tile(cfg, a, w, tile_k=LANES_PER_O)
    vectors.append(TestVector(
        name="distinct_lanes",
        tile_k=LANES_PER_O,
        num_cycles=1,
        a_cycles=[pack_activation(a)],
        w_cycles=[pack_weights(w)],
        expected=pack_outputs(expected),
    ))

    # --- Signed extremes: w=-8, a=127 (max negative × max positive) ---
    a = [127] * LANES_PER_O
    w = [[-8] * LANES_PER_O for _ in range(TILE_O)]
    expected = dot_tile(cfg, a, w, tile_k=LANES_PER_O)
    vectors.append(TestVector(
        name="extreme_neg8_pos127",
        tile_k=LANES_PER_O,
        num_cycles=1,
        a_cycles=[pack_activation(a)],
        w_cycles=[pack_weights(w)],
        expected=pack_outputs(expected),
    ))

    # --- Signed extremes: w=7, a=-128 (max positive × max negative) ---
    a = [-128] * LANES_PER_O
    w = [[7] * LANES_PER_O for _ in range(TILE_O)]
    expected = dot_tile(cfg, a, w, tile_k=LANES_PER_O)
    vectors.append(TestVector(
        name="extreme_pos7_neg128",
        tile_k=LANES_PER_O,
        num_cycles=1,
        a_cycles=[pack_activation(a)],
        w_cycles=[pack_weights(w)],
        expected=pack_outputs(expected),
    ))

    # --- All max = 7*127 (accumulator stress) ---
    a_vec = [127] * (TILE_O * LANES_PER_O)  # enough for multi-cycle
    w_mat = [[7] * (TILE_O * LANES_PER_O) for _ in range(TILE_O)]
    for tk in [LANES_PER_O, LANES_PER_O * 2, LANES_PER_O * 8]:
        a = a_vec[:tk]
        w_tk = [row[:tk] for row in w_mat]
        expected = dot_tile(cfg, a, w_tk, tile_k=tk)
        cycles = cfg.cycles_for_tile_k(tk)
        a_cycles_list = []
        w_cycles_list = []
        for cyc in range(cycles):
            start = cyc * LANES_PER_O
            end = min(start + LANES_PER_O, tk)
            a_sl = a[start:end] + [0] * (LANES_PER_O - (end - start))
            w_sl = []
            for o in range(TILE_O):
                w_row = w_tk[o][start:end] + [0] * (LANES_PER_O - (end - start))
                w_sl.append(w_row)
            a_cycles_list.append(pack_activation(a_sl))
            w_cycles_list.append(pack_weights(w_sl))
        vectors.append(TestVector(
            name=f"acc_stress_tk{tk}",
            tile_k=tk,
            num_cycles=cycles,
            a_cycles=a_cycles_list,
            w_cycles=w_cycles_list,
            expected=pack_outputs(expected),
        ))

    # --- Non-power-of-2 tile_k: 3, 7, 31 ---
    for tk in [1, 3, 7, 31]:
        a = [rand_int8() for _ in range(tk)]
        w = [[rand_int4() for _ in range(tk)] for _ in range(TILE_O)]
        expected = dot_tile(cfg, a, w, tile_k=tk)
        cycles = cfg.cycles_for_tile_k(tk)
        a_cycles_list = []
        w_cycles_list = []
        for cyc in range(cycles):
            start = cyc * LANES_PER_O
            end = min(start + LANES_PER_O, tk)
            a_sl = a[start:end] + [0] * (LANES_PER_O - (end - start))
            w_sl = []
            for o in range(TILE_O):
                w_row = w[o][start:end] + [0] * (LANES_PER_O - (end - start))
                w_sl.append(w_row)
            a_cycles_list.append(pack_activation(a_sl))
            w_cycles_list.append(pack_weights(w_sl))
        vectors.append(TestVector(
            name=f"odd_tk{tk}",
            tile_k=tk,
            num_cycles=cycles,
            a_cycles=a_cycles_list,
            w_cycles=w_cycles_list,
            expected=pack_outputs(expected),
        ))

    return vectors


def gen_random(n: int = 200, seed: int = 42) -> List[TestVector]:
    """Generate random test vectors."""
    cfg = TileConfig(lanes=LANES, tile_o=TILE_O)
    rng = random.Random(seed)
    vectors = []

    tile_k_options = [1, 2, 3, 4, 7, 8, 16, 31, 32, 64, 127, 128, 256]
    for i in range(n):
        tk = rng.choice(tile_k_options)
        a = [rand_int8() for _ in range(tk)]
        w = [[rand_int4() for _ in range(tk)] for _ in range(TILE_O)]
        expected = dot_tile(cfg, a, w, tile_k=tk)
        cycles = cfg.cycles_for_tile_k(tk)
        a_cycles_list = []
        w_cycles_list = []
        for cyc in range(cycles):
            start = cyc * LANES_PER_O
            end = min(start + LANES_PER_O, tk)
            a_sl = a[start:end] + [0] * (LANES_PER_O - (end - start))
            w_sl = []
            for o in range(TILE_O):
                w_row = w[o][start:end] + [0] * (LANES_PER_O - (end - start))
                w_sl.append(w_row)
            a_cycles_list.append(pack_activation(a_sl))
            w_cycles_list.append(pack_weights(w_sl))
        vectors.append(TestVector(
            name=f"rand_{i:04d}_tk{tk}",
            tile_k=tk,
            num_cycles=cycles,
            a_cycles=a_cycles_list,
            w_cycles=w_cycles_list,
            expected=pack_outputs(expected),
        ))

    return vectors


def emit_tb(vectors: List[TestVector], filename: str):
    """Write a complete self-checking SystemVerilog testbench."""
    with open(filename, 'w') as f:
        f.write("""`timescale 1ns / 1ps

// Auto-generated self-checking testbench for dot_int4_tile (128-lane).
// Vectors generated by tools/llmsim/golden.py
module tb;
    localparam LANES     = 128;
    localparam TILE_O    = 32;
    localparam LANES_PER_O = LANES / TILE_O;
    localparam ACC_WIDTH = 32;
    localparam AW = LANES_PER_O * 8;
    localparam WW = LANES * 4;
    localparam OW = TILE_O * ACC_WIDTH;

    logic clk, rst_n;
    integer failures, passes;

    always #5 clk = ~clk;

    logic                       in_valid;
    logic [AW-1:0]              in_a_data;
    logic [WW-1:0]              in_w_data;
    logic                       in_last;
    logic                       in_ready;

    logic                       out_valid;
    logic [OW-1:0]              out_data;
    logic                       out_ready;

    dot_int4_tile #(
        .LANES(LANES), .TILE_O(TILE_O), .ACC_WIDTH(ACC_WIDTH)
    ) dut (
        .clk, .rst_n,
        .in_valid, .in_a_data, .in_w_data, .in_last, .in_ready,
        .out_valid, .out_data, .out_ready
    );

    function logic signed [ACC_WIDTH-1:0] out_ch;
        input integer ch;
        begin
            out_ch = $signed(out_data[ch * ACC_WIDTH +: ACC_WIDTH]);
        end
    endfunction

    // Expected output for current test (set before each check_output call)
    logic [OW-1:0] expected_data;

    task wait_ready;
    begin
        while (!in_ready) @(posedge clk);
    end
    endtask

    task wait_valid;
    begin
        while (!out_valid) @(posedge clk);
    end
    endtask

    task check_output;
        input string  name;
        input integer tk;
        integer o;
        logic fail_flag;
        begin
            wait_valid();
            fail_flag = 0;
            for (o = 0; o < TILE_O; o++) begin
                if (out_ch(o) !== $signed(expected_data[o*ACC_WIDTH +: ACC_WIDTH])) begin
                    if (!fail_flag) begin
                        $display("FAIL %s (tile_k=%0d)", name, tk);
                        fail_flag = 1;
                    end
                    $display("  ch[%0d]: got %0d, exp %0d", o,
                        out_ch(o),
                        $signed(expected_data[o*ACC_WIDTH +: ACC_WIDTH]));
                    failures = failures + 1;
                end else begin
                    passes = passes + 1;
                end
            end
            @(posedge clk);
            out_ready <= 0;
        end
    endtask

    initial begin : test_main
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);
        clk = 0; rst_n = 0; in_valid <= 0; out_ready <= 0;
        failures = 0; passes = 0;
        #40; rst_n = 1; #10;

""")

        # Emit each test vector as inline code
        for i, v in enumerate(vectors):
            f.write(f"        // --- {v.name} (tile_k={v.tile_k}) ---\n")
            f.write(f"        wait_ready();\n")
            for cyc in range(v.num_cycles):
                a_hex = f"32'h{v.a_cycles[cyc]:08X}"
                w_hex = f"512'h{v.w_cycles[cyc]:0128X}"
                last = "1" if cyc == v.num_cycles - 1 else "0"
                f.write(f"        in_a_data <= {a_hex};\n")
                f.write(f"        in_w_data <= {w_hex};\n")
                f.write(f"        in_valid  <= 1;\n")
                f.write(f"        in_last   <= {last};\n")
                f.write(f"        @(posedge clk);\n")
            f.write(f"        in_valid <= 0;\n")
            f.write(f"        out_ready <= 1;\n")

            # Set expected_data as flat packed value
            exp_hex = f"1024'h{v.expected:0256X}"
            f.write(f"        expected_data = {exp_hex};\n")

            name = v.name.replace('"', '\\"')
            f.write(f'        check_output("{name}", {v.tile_k});\n')
            f.write(f"\n")

        f.write(f"""
        if (failures == 0)
            $display("\\nALL PASS (%0d vectors, %0d channel checks)", {len(vectors)}, passes);
        else
            $display("\\nFAIL: %0d failures", failures);
        $finish;
    end

endmodule
""")
    n_channels = len(vectors) * TILE_O
    print(f"Total channel checks: {n_channels}")


def main():
    random.seed(42)

    det = gen_deterministic()
    rand = gen_random(n=200, seed=12345)
    all_vectors = det + rand

    out = sys.argv[1] if len(sys.argv) > 1 else "tb/dot_tile_tb_gen.sv"
    emit_tb(all_vectors, out)
    print(f"Generated {len(all_vectors)} test vectors → {out}")
    print(f"  Deterministic: {len(det)}")
    print(f"  Random: {len(rand)}")


if __name__ == "__main__":
    main()

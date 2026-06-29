`timescale 1ns / 1ps

module tb;
    localparam LANES     = 128;
    localparam TILE_O    = 32;
    localparam LANES_PER_O = LANES / TILE_O;
    localparam ACC_WIDTH = 32;

    localparam AW = LANES_PER_O * 8;
    localparam WW = LANES * 4;
    localparam OW = TILE_O * ACC_WIDTH;

    logic clk, rst_n;
    integer failures;
    integer passes;

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

    function logic [AW-1:0] pack_a;
        input logic signed [7:0] a0, a1, a2, a3;
        begin
            pack_a = {a3, a2, a1, a0};
        end
    endfunction

    function logic [WW-1:0] pack_w_slice;
        input logic signed [3:0] w00, w01, w02, w03;
        input logic signed [3:0] w10, w11, w12, w13;
        input logic signed [3:0] w20, w21, w22, w23;
        input logic signed [3:0] w30, w31, w32, w33;
        input logic signed [3:0] w40, w41, w42, w43;
        input logic signed [3:0] w50, w51, w52, w53;
        input logic signed [3:0] w60, w61, w62, w63;
        input logic signed [3:0] w70, w71, w72, w73;
        input logic signed [3:0] w80, w81, w82, w83;
        input logic signed [3:0] w90, w91, w92, w93;
        input logic signed [3:0] w100, w101, w102, w103;
        input logic signed [3:0] w110, w111, w112, w113;
        input logic signed [3:0] w120, w121, w122, w123;
        input logic signed [3:0] w130, w131, w132, w133;
        input logic signed [3:0] w140, w141, w142, w143;
        input logic signed [3:0] w150, w151, w152, w153;
        input logic signed [3:0] w160, w161, w162, w163;
        input logic signed [3:0] w170, w171, w172, w173;
        input logic signed [3:0] w180, w181, w182, w183;
        input logic signed [3:0] w190, w191, w192, w193;
        input logic signed [3:0] w200, w201, w202, w203;
        input logic signed [3:0] w210, w211, w212, w213;
        input logic signed [3:0] w220, w221, w222, w223;
        input logic signed [3:0] w230, w231, w232, w233;
        input logic signed [3:0] w240, w241, w242, w243;
        input logic signed [3:0] w250, w251, w252, w253;
        input logic signed [3:0] w260, w261, w262, w263;
        input logic signed [3:0] w270, w271, w272, w273;
        input logic signed [3:0] w280, w281, w282, w283;
        input logic signed [3:0] w290, w291, w292, w293;
        input logic signed [3:0] w300, w301, w302, w303;
        input logic signed [3:0] w310, w311, w312, w313;
        begin
            pack_w_slice = {
                w313, w312, w311, w310,
                w303, w302, w301, w300,
                w293, w292, w291, w290,
                w283, w282, w281, w280,
                w273, w272, w271, w270,
                w263, w262, w261, w260,
                w253, w252, w251, w250,
                w243, w242, w241, w240,
                w233, w232, w231, w230,
                w223, w222, w221, w220,
                w213, w212, w211, w210,
                w203, w202, w201, w200,
                w193, w192, w191, w190,
                w183, w182, w181, w180,
                w173, w172, w171, w170,
                w163, w162, w161, w160,
                w153, w152, w151, w150,
                w143, w142, w141, w140,
                w133, w132, w131, w130,
                w123, w122, w121, w120,
                w113, w112, w111, w110,
                w103, w102, w101, w100,
                w93, w92, w91, w90,
                w83, w82, w81, w80,
                w73, w72, w71, w70,
                w63, w62, w61, w60,
                w53, w52, w51, w50,
                w43, w42, w41, w40,
                w33, w32, w31, w30,
                w23, w22, w21, w20,
                w13, w12, w11, w10,
                w03, w02, w01, w00
            };
        end
    endfunction

    function logic signed [ACC_WIDTH-1:0] ref_dot;
        input integer tk;
        input integer o_ch;
        // We store weights and activations in module-level arrays for ref computation
        begin
            ref_dot = 0;
        end
    endfunction

    function logic signed [ACC_WIDTH-1:0] out_ch;
        input integer ch;
        begin
            out_ch = $signed(out_data[ch * ACC_WIDTH +: ACC_WIDTH]);
        end
    endfunction

    // Module-level arrays for test data
    logic signed [3:0] w_ref [TILE_O-1:0][127:0];
    logic signed [7:0] a_ref [127:0];
    integer tile_k_cur;

    task compute_ref;
        integer o, k;
        logic signed [ACC_WIDTH-1:0] expected [TILE_O-1:0];
        begin
            for (o = 0; o < TILE_O; o++) begin
                expected[o] = 0;
                for (k = 0; k < tile_k_cur; k++)
                    expected[o] = expected[o] + $signed(w_ref[o][k]) * $signed(a_ref[k]);
            end

            // Wait for result
            out_ready = 1;
            while (!out_valid) @(posedge clk);
            for (o = 0; o < TILE_O; o++) begin
                if (out_ch(o) !== expected[o]) begin
                    failures = failures + 1;
                    $display("FAIL ch[%0d]: got %0d, exp %0d", o, out_ch(o), expected[o]);
                end else begin
                    passes = passes + 1;
                end
            end
            @(posedge clk);
            out_ready = 0;
        end
    endtask

    task feed_one_cycle;
        input integer cyc;
        input integer tk;
        input logic is_last;
        integer o, l, k;
        begin
            // Set activations for this cycle
            {in_a_data[1*8+:8], in_a_data[0*8+:8]} = '0;
            {in_a_data[3*8+:8], in_a_data[2*8+:8]} = '0;
            for (l = 0; l < LANES_PER_O; l++) begin
                k = cyc * LANES_PER_O + l;
                if (k < tk)
                    in_a_data[l*8 +: 8] = a_ref[k];
                else
                    in_a_data[l*8 +: 8] = 8'sd0;
            end

            // Pack weights for all output channels
            for (o = 0; o < TILE_O; o++) begin
                for (l = 0; l < LANES_PER_O; l++) begin
                    k = cyc * LANES_PER_O + l;
                    if (k < tk)
                        in_w_data[(o * LANES_PER_O + l)*4 +: 4] = w_ref[o][k];
                    else
                        in_w_data[(o * LANES_PER_O + l)*4 +: 4] = 4'sd0;
                end
            end

            in_valid = 1;
            in_last  = is_last;
            @(posedge clk);
        end
    endtask

    task feed_tile;
        input integer tk;
        integer c, cycles;
        begin
            tile_k_cur = tk;
            cycles = (tk + LANES_PER_O - 1) / LANES_PER_O;

            while (!in_ready) @(posedge clk);

            for (c = 0; c < cycles; c++)
                feed_one_cycle(c, tk, c == cycles - 1);

            in_valid = 0;
            compute_ref();
        end
    endtask

    initial begin : test_main
        integer o, k, tk;
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);

        clk = 0; rst_n = 0; in_valid = 0; out_ready = 0;
        failures = 0; passes = 0;
        #40; rst_n = 1; #10;

        // --- Test 1: Single-cycle (tile_k=4) ---
        $display("=== Test 1: Single-cycle (tile_k=4) ===");
        tk = 4;
        a_ref[0] = 8'sd3;  a_ref[1] = 8'sd5;  a_ref[2] = -8'sd7; a_ref[3] = 8'sd2;
        for (o = 0; o < TILE_O; o++) begin
            w_ref[o][0] = 1;  w_ref[o][1] = -2;
            w_ref[o][2] = 3;  w_ref[o][3] = -1;
        end
        feed_tile(tk);

        // --- Test 2: Multi-cycle (tile_k=8) ---
        $display("=== Test 2: Multi-cycle (tile_k=8) ===");
        tk = 8;
         for (k = 0; k < tk; k++)
            a_ref[k] = k + 1;
        for (o = 0; o < TILE_O; o++) begin
            for (k = 0; k < tk; k++)
                w_ref[o][k] = (k % 8) - 3;
        end
        feed_tile(tk);

        // --- Test 3: Back-to-back tiles ---
        $display("=== Test 3: Back-to-back tiles ===");
        tk = 4;
        a_ref[0] = 8'sd1; a_ref[1] = 8'sd2; a_ref[2] = 8'sd3; a_ref[3] = 8'sd4;
        for (o = 0; o < TILE_O; o++)
            for (k = 0; k < tk; k++)
                w_ref[o][k] = 1;
        feed_tile(tk);

        a_ref[0] = -8'sd1; a_ref[1] = -8'sd2; a_ref[2] = -8'sd3; a_ref[3] = -8'sd4;
        for (o = 0; o < TILE_O; o++)
            for (k = 0; k < tk; k++)
                w_ref[o][k] = 2;
        feed_tile(tk);

        // --- Test 4: Random (tile_k=32) ---
        $display("=== Test 4: Random (tile_k=32) ===");
        tk = 32;
        for (k = 0; k < tk; k++)
            a_ref[k] = ($random % 256) - 128;
        for (o = 0; o < TILE_O; o++)
            for (k = 0; k < tk; k++)
                w_ref[o][k] = ($random % 16) - 8;
        feed_tile(tk);

        if (failures == 0)
            $display("\nALL PASS (%0d checks)", passes);
        else
            $display("\n%0d FAIL, %0d PASS", failures, passes);
        $finish;
    end

endmodule

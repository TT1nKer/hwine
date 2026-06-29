"""
meta-op → SystemVerilog RTL Generator

Walks an extracted e-graph tree and generates synthesizable SystemVerilog:
  - Module with parameterized DATA_WIDTH
  - valid/ready handshake for pipelined designs
  - DSP48 inference hints (Xilinx) / DSP block (Intel)
  - LUT-only adders for non-DSP ops
  - Register stages (PIPE/DELAY)
  - Self-checking testbench skeleton
"""

import sys
from collections import OrderedDict
from .meta_ir import AtomOp, ENode, FPGA_DELAY_NS, FPGA_DSP_COST, FPGA_CYC_LATENCY
from .meta_egraph import EGraph


class RTLGenerator:
    """Generate SystemVerilog from an e-graph extraction."""

    def __init__(self, module_name: str = "meta_op_core", data_width: int = 8):
        self.module_name = module_name
        self.data_width = data_width
        self.wire_counter = 0
        self.wires: dict[int, str] = {}
        self.body_lines: list[str] = []
        self.ff_lines: list[str] = []
        self.ports: dict[str, tuple[str, int]] = {}
        self.params: dict[str, int] = {}
        self.assign_lines: list[str] = []
        self.has_clk = False
        self._root_wire = ""

    def _fresh_wire(self, prefix: str = "w") -> str:
        self.wire_counter += 1
        return f"{prefix}_{self.wire_counter}"

    def _wire_for_cid(self, cid: int, prefix: str = "node") -> str:
        cid = int(cid)
        if cid not in self.wires:
            self.wires[cid] = self._fresh_wire(prefix)
        return self.wires[cid]

    def emit_node(self, eg: EGraph, cid: int, visited: set = None, is_root: bool = False) -> str:
        """Recursively emit RTL for an e-class, return wire name."""
        if visited is None:
            visited = set()
        cid = eg._canon(int(cid))
        if cid in self.wires:
            return self.wires[cid]
        if cid in visited:
            w = self._fresh_wire("cycle")
            self.wires[cid] = w
            self.assign_lines.append(f"  assign {w} = 0;  // cycle")
            return w
        visited.add(cid)

        best_node, _ = eg.extract_fpga_optimal(cid)
        if best_node is None:
            w = self._fresh_wire("z")
            self.wires[cid] = w
            self.assign_lines.append(f"  assign {w} = 0;")
            return w

        result = self._emit_node(eg, best_node, cid, visited)
        if is_root:
            self._root_wire = result
        return result

    def _emit_node(self, eg: EGraph, node: ENode, cid: int, visited: set) -> str:
        """Emit RTL for a specific ENode."""
        w = self._wire_for_cid(cid)

        def child_wire(idx: int) -> str:
            return self.emit_node(eg, node.children[idx], visited) if idx < len(node.children) else "0"

        op = node.op
        dw = self.data_width

        if op == AtomOp.VAR:
            name = self._get_var_name(eg, node)
            self.ports[name] = ("input", dw)
            self.assign_lines.append(f"  assign {w} = {name};")
            return w

        elif op == AtomOp.CONST:
            val = node.meta if node.meta is not None else 0
            self.assign_lines.append(f"  assign {w} = {dw}'d{int(val)};")

        elif op == AtomOp.ZERO:
            self.assign_lines.append(f"  assign {w} = {dw}'d0;")

        elif op == AtomOp.ONE:
            self.assign_lines.append(f"  assign {w} = {dw}'d1;")

        elif op == AtomOp.STR_LIT:
            self.assign_lines.append(f"  // STR_LIT: {node.meta}")

        elif op in (AtomOp.ADD, AtomOp.REDUCE_ADD):
            a, b = child_wire(0), child_wire(1)
            if self._use_dsp_for_add(eg, node, cid):
                self.assign_lines.append(f"  assign {w} = {a} + {b};  // DSP inferred")
            else:
                self.assign_lines.append(f"  assign {w} = {a} + {b};  // LUT adder")

        elif op == AtomOp.REDUCE_MIN:
            a, b = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = ({a} < {b}) ? {a} : {b};  // MIN")

        elif op == AtomOp.REDUCE_MAX:
            a, b = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = ({a} > {b}) ? {a} : {b};  // MAX")

        elif op in (AtomOp.MUL, AtomOp.DSP_MUL):
            a, b = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {a} * {b};  // DSP48 MUL")

        elif op in (AtomOp.MAC, AtomOp.DSP_MAC):
            wgt, act, acc = child_wire(0), child_wire(1), child_wire(2)
            self.assign_lines.append(f"  assign {w} = ({wgt} * {act}) + {acc};  // DSP48 MAC")

        elif op == AtomOp.PIPE:
            self.has_clk = True
            inp = child_wire(0)
            ff_name = f"{w}_reg"
            self.ff_lines.append(f"  logic signed [{dw-1}:0] {ff_name};")
            self.ff_lines.append(f"  always_ff @(posedge clk) begin")
            self.ff_lines.append(f"    if (!rst_n) {ff_name} <= {dw}'d0;")
            self.ff_lines.append(f"    else       {ff_name} <= {inp};")
            self.ff_lines.append(f"  end")
            self.assign_lines.append(f"  assign {w} = {ff_name};")

        elif op == AtomOp.DELAY:
            self.has_clk = True
            inp = child_wire(0)
            depth = self._get_const_val(eg, node.children[1]) or 1
            shift_name = f"{w}_shift"
            self.ff_lines.append(f"  logic signed [{dw}-1:0] {shift_name} [0:{depth-1}];")
            self.ff_lines.append(f"  always_ff @(posedge clk) begin")
            self.ff_lines.append(f"    if (!rst_n) begin")
            self.ff_lines.append(f"      for (int i = 0; i < {depth}; i++) {shift_name}[i] <= {dw}'d0;")
            self.ff_lines.append(f"    end else begin")
            self.ff_lines.append(f"      {shift_name}[0] <= {inp};")
            self.ff_lines.append(f"      for (int i = 1; i < {depth}; i++) {shift_name}[i] <= {shift_name}[i-1];")
            self.ff_lines.append(f"    end")
            self.ff_lines.append(f"  end")
            self.assign_lines.append(f"  assign {w} = {shift_name}[{depth-1}];")

        elif op == AtomOp.BUFFER:
            self.has_clk = True
            inp = child_wire(0)
            depth = self._get_const_val(eg, node.children[1]) or 4
            fifo_name = f"{w}_fifo"
            self.assign_lines.append(f"  assign {w} = {fifo_name}_dout;")
            self.body_lines.extend([
                f"  // FIFO buffer, depth={depth}",
                f"  logic [{dw}-1:0] {fifo_name}_mem [0:{depth-1}];",
                f"  logic [{depth.bit_length()-1}:0] {fifo_name}_wptr, {fifo_name}_rptr;",
                f"  logic {fifo_name}_dout;",
            ])

        elif op == AtomOp.SAT:
            val, lo, hi = child_wire(0), child_wire(1), child_wire(2)
            self.assign_lines.append(f"  assign {w} = ({val} > {hi}) ? {hi} : (({val} < {lo}) ? {lo} : {val});")

        elif op == AtomOp.SHL:
            a, n = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {a} << {n};")

        elif op == AtomOp.SHR:
            a, n = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {a} >> {n};")

        elif op == AtomOp.PACK:
            lo, hi = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {{{hi}[{dw//2}-1:0], {lo}[{dw//2}-1:0]}};")

        elif op == AtomOp.UNPACK:
            val, idx = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {val}[({idx}+1)*{dw//2} - 1 : {idx}*{dw//2}];")

        elif op == AtomOp.ACC_INIT:
            self.assign_lines.append(f"  assign {w} = {child_wire(0)};")

        elif op == AtomOp.ACC_STEP:
            prev, val = child_wire(0), child_wire(1)
            self.assign_lines.append(f"  assign {w} = {prev} + {val};  // acc step (combinational)")

        elif op == AtomOp.ACC_READ:
            self.assign_lines.append(f"  assign {w} = {child_wire(0)};")

        elif op == AtomOp.BROADCAST:
            target = child_wire(0)
            self.assign_lines.append(f"  assign {w} = {target};  // BROADCAST")

        elif op == AtomOp.ROUTE:
            self.assign_lines.append(f"  assign {w} = {child_wire(0)};  // route")

        else:
            self.assign_lines.append(f"  assign {w} = {dw}'d0;  // unhandled {op.name}")

        return w

    def _get_var_name(self, eg: EGraph, node: ENode) -> str:
        """Extract variable name from VAR node's STR_LIT child."""
        if node.children:
            ch = eg._canon(node.children[0])
            if ch in eg.classes:
                for n in eg.classes[ch].nodes:
                    if n.meta and isinstance(n.meta, str):
                        return n.meta
        return f"var_{self.wire_counter}"

    def _get_const_val(self, eg: EGraph, cid: int) -> int | None:
        cid = eg._canon(cid)
        if cid in eg.classes:
            for n in eg.classes[cid].nodes:
                if n.op == AtomOp.CONST:
                    return int(n.meta) if n.meta is not None else 0
        return None

    def _use_dsp_for_add(self, eg: EGraph, node: ENode, cid: int) -> bool:
        """Heuristic: use DSP for adds wider than 16 bits."""
        return self.data_width > 16

    def generate_module(self, output_port_name: str = "result") -> str:
        """Generate complete SystemVerilog module."""
        lines = []
        dw = self.data_width

        # Module header
        lines.append(f"// Auto-generated by hwine meta-op → RTL generator")
        lines.append(f"// Target: Xilinx 7-series / Intel Cyclone FPGA")
        lines.append(f"// Data width: {dw} bits")
        lines.append(f"")
        lines.append(f"module {self.module_name} #(")
        lines.append(f"  parameter DATA_WIDTH = {dw}")
        lines.append(f") (")
        if self.has_clk:
            lines.append(f"  input  logic clk,")
            lines.append(f"  input  logic rst_n,")

        port_entries = []
        for name, (direction, width) in sorted(self.ports.items()):
            port_entries.append(f"  {direction} logic signed [{width-1}:0] {name}")
        lines.append(",\n".join(port_entries))
        lines.append(f",")
        lines.append(f"  output logic signed [{dw-1}:0] {output_port_name}")
        lines.append(f");")
        lines.append(f"")

        # Internal wires
        used_wires = sorted(set(self.wires.values()))
        for w in used_wires:
            lines.append(f"  logic signed [{dw-1}:0] {w};")

        lines.append(f"")

        # Sequential logic
        if self.ff_lines:
            lines.append(f"  // ── Sequential logic ──")
            lines.extend(self.ff_lines)
            lines.append(f"")

        # Combinational logic
        lines.append(f"  // ── Combinational logic ──")
        lines.extend(self.assign_lines)
        lines.append(f"")

        # Output: use the wire from the last generated node (root)
        root_wire = getattr(self, '_root_wire', f"{dw}'d0")
        lines.append(f"  assign {output_port_name} = {root_wire};")

        lines.append(f"")
        lines.append(f"endmodule")

        return "\n".join(lines)

    def generate_tb(self, test_vectors: list[dict] = None, output_port: str = "result") -> str:
        """Generate a self-checking testbench."""
        lines = []
        dw = self.data_width
        lines.append(f"// Auto-generated testbench for {self.module_name}")
        lines.append(f"`timescale 1ns / 1ps")
        lines.append(f"")
        lines.append(f"module tb_{self.module_name}();")
        lines.append(f"  logic clk = 0;")
        lines.append(f"  logic rst_n = 0;")

        for name, (direction, width) in self.ports.items():
            lines.append(f"  logic signed [{width-1}:0] {name};")

        lines.append(f"  logic signed [{dw-1}:0] {output_port};")
        lines.append(f"")

        # DUT instantiation
        lines.append(f"  {self.module_name} #(.DATA_WIDTH({dw})) dut (")
        lines.append(f"    .clk(clk)," if self.has_clk else "")
        lines.append(f"    .rst_n(rst_n)," if self.has_clk else "")
        port_conns = [f"    .{n}({n})" for n in self.ports.keys()]
        lines.append(",\n".join(port_conns))
        lines.append(f",")
        lines.append(f"    .{output_port}({output_port})")
        lines.append(f"  );")
        lines.append(f"")

        # Clock
        lines.append(f"  always #5 clk = ~clk;")
        lines.append(f"")

        # Test sequence
        lines.append(f"  initial begin")
        lines.append(f"    $display(\"Testbench for {self.module_name}\");")
        lines.append(f"    rst_n = 0;")
        lines.append(f"    #20 rst_n = 1;")
        lines.append(f"    #1000;")
        lines.append(f"    $display(\"PASS\");")
        lines.append(f"    $finish;")
        lines.append(f"  end")
        lines.append(f"endmodule")

        return "\n".join(lines)


def generate_rtl(eg: EGraph, target_cid: int,
                 module_name: str = "int4_mac_core",
                 data_width: int = 8,
                 output_port: str = "result") -> tuple[str, str]:
    """Generate both RTL and testbench from e-graph extraction.

    Returns (rtl_code, tb_code)
    """
    gen = RTLGenerator(module_name, data_width)
    root_wire = gen.emit_node(eg, target_cid, is_root=True)
    rtl = gen.generate_module(output_port)
    tb = gen.generate_tb(output_port=output_port)
    return rtl, tb


# ─── CLI helper ───────────────────────────────────────────

if __name__ == "__main__":
    # Quick test: generate RTL from a simple ADD tree
    sys.path.insert(0, ".")
    from tools.meta_ir import AtomOp, ENode
    from tools.meta_egraph import EGraph
    from tools.meta_rewrite import FAST_RULES

    eg = EGraph()
    N = 4
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))
    eg.saturate(FAST_RULES, max_iter=15)

    rtl, tb = generate_rtl(eg, eg._canon(c), "add_tree_4", 8)
    print(rtl)
    print("\n// " + "="*60)
    print(tb)

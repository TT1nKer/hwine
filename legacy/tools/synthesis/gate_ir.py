"""
Gate-level IR: the lowest granularity.
Only 6 primitives: NOT, AND, OR, XOR, MUX, REG (DFF).
All higher-level constructs decompose to these.

Every signal is a single wire (1-bit). Width > 1 = multiple wires.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Op(Enum):
    NOT  = auto()   # out = ~in
    AND  = auto()   # out = a & b
    OR   = auto()   # out = a | b
    XOR  = auto()   # out = a ^ b
    MUX  = auto()   # out = sel ? a : b
    REG  = auto()   # out = d on next clk (sequential)


# Cost models
OP_DELAY = {Op.NOT: 1, Op.AND: 1.5, Op.OR: 1.5, Op.XOR: 2.5, Op.MUX: 2.0, Op.REG: 1.0}
OP_AREA  = {Op.NOT: 1, Op.AND: 2,   Op.OR: 2,   Op.XOR: 4,   Op.MUX: 3,   Op.REG: 4}

# Identity constants
ZERO = 0  # constant 0
ONE  = 1  # constant 1


@dataclass(frozen=True, order=True)
class GateNode:
    """A single gate in the circuit graph. Immutable."""
    op: Op
    args: tuple  # (node_id, ...) — can be int for constants/inputs, or str for intermediate nodes

    def __repr__(self):
        arg_str = ", ".join(str(a) for a in self.args)
        return f"{self.op.name}({arg_str})"


@dataclass
class Circuit:
    """A named collection of gates with designated outputs."""
    name: str
    gates: dict[str, GateNode] = field(default_factory=dict)   # node_id → GateNode
    outputs: dict[str, str] = field(default_factory=dict)      # output_name → node_id

    def add_gate(self, name: str, op: Op, *args):
        self.gates[name] = GateNode(op, args)
        return self

    def add_output(self, name: str, node_id: str):
        self.outputs[name] = node_id
        return self

    def node_count(self) -> int:
        return len(self.gates)

    def depth(self) -> int:
        """Compute longest combinational path from input to any output."""
        memo = {}

        def path_depth(nid: str, visiting: set) -> int:
            if nid in memo:
                return memo[nid]
            if nid not in self.gates:
                return 0  # input/constant
            if nid in visiting:
                return 0  # cycle
            node = self.gates[nid]
            max_child = 0
            visiting.add(nid)
            for child in node.args:
                if isinstance(child, str):
                    max_child = max(max_child, path_depth(child, visiting))
            visiting.discard(nid)
            memo[nid] = max_child + OP_DELAY[node.op]
            return memo[nid]

        max_d = 0
        for out_nid in self.outputs.values():
            max_d = max(max_d, path_depth(out_nid, set()))
        return max_d

    def total_area(self) -> float:
        return sum(OP_AREA[g.op] for g in self.gates.values())

    def dump(self) -> str:
        lines = [f"Circuit: {self.name}"]
        lines.append(f"  gates: {len(self.gates)}, depth: {self.depth()}, area: {self.total_area()}")
        for nid, gate in self.gates.items():
            lines.append(f"  {nid} = {gate}")
        for oname, nid in self.outputs.items():
            lines.append(f"  output {oname} = {nid}")
        return "\n".join(lines)

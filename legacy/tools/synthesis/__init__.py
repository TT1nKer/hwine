"""
Bit-level synthesis: e-graph based optimization of gate-level circuits.
Decompose everything to the lowest granularity and let algebraic rewrite
rules discover optimal structures.
"""

from .gate_ir import Op, GateNode, Circuit
from .egraph import EGraph, ENode
from .rewrite import apply_all, ensure_constants
from .extract import extract_optimal

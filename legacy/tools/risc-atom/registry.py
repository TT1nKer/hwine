"""
Atom Registry: defines every available atomic operation.
Each atom is a function: AtomValue... → AtomValue.
Each atom has a unique opcode, typed inputs, typed output, and a cost.
"""

from dataclasses import dataclass
from typing import Callable, Any

from .types import AtomValue


@dataclass(frozen=True)
class AtomSig:
    """Signature of one atomic operation."""
    opcode: str
    description: str
    input_types: tuple[str, ...]   # "graph", "signal", "module", "schedule", "ilp", "str", "int"
    output_type: str
    cost: int = 1                  # abstract cost (1 = trivial, 10 = expensive)


# ============================================================
# Complete atom registry
# ============================================================

ATOMS: dict[str, AtomSig] = {}

def register(opcode: str, desc: str, inputs: tuple[str, ...],
             output: str, cost: int = 1):
    ATOMS[opcode] = AtomSig(opcode, desc, inputs, output, cost)


# --- Graph atoms ---
register("graph_new",        "create empty graph",                          (),                        "graph")
register("graph_add_node",   "add a node to a graph",                      ("graph", "str", "str"),  "graph")
register("graph_add_edge",   "add a directed edge between two nodes",      ("graph", "str", "str"),  "graph")
register("graph_rm_node",    "remove a node and its incident edges",       ("graph", "str"),          "graph")
register("graph_rm_edge",    "remove an edge from a graph",                ("graph", "str", "str"),  "graph")
register("graph_topo_sort",  "topological sort of graph nodes",            ("graph",),                "topolist")
register("graph_trans_red",  "transitive reduction of a graph",            ("graph",),                "graph")

# --- Signal atoms ---
register("signal_new",       "create a new signal",                        ("str", "int"),            "signal", cost=1)
register("signal_concat",    "concatenate two signals",                    ("signal", "signal"),      "signal", cost=2)
register("signal_slice",     "slice a signal [hi:lo]",                     ("signal", "int", "int"),  "signal", cost=1)

# --- Module atoms ---
register("module_new",       "create an empty module",                     ("str",),                  "module")
register("module_add_port",  "add an input/output port to a module",       ("module", "str", "str", "signal"), "module", cost=2)
register("module_add_assign","add a continuous assignment",                ("module", "str", "str"),  "module", cost=1)
register("module_add_ff",    "add a flip-flop always block",               ("module", "str", "str"),  "module", cost=3)
register("module_add_inst",  "add a submodule instance",                   ("module", "str", "str"),  "module", cost=2)
register("module_emit",      "emit synthesizable Verilog",                 ("module",),               "str", cost=5)

# --- Schedule atoms ---
register("sched_new",        "create empty schedule from a CDFG",          ("graph",),                "schedule")
register("sched_asap",       "ASAP schedule: assign earliest possible cycles", ("graph",),             "schedule", cost=3)
register("sched_alap",       "ALAP schedule: assign latest possible cycles",   ("graph", "int"),       "schedule", cost=3)
register("sched_list",       "list scheduling with resource constraints",       ("graph", "int"),       "schedule", cost=8)
register("sched_sdc",        "SDC scheduling via linear constraints",           ("graph", "int"),       "schedule", cost=15)
register("sched_assign_op",  "manually assign an op to a cycle",                ("schedule", "str", "int"), "schedule", cost=1)

# --- ILP atoms ---
register("ilp_new",          "create ILP model",                          (),                        "ilp")
register("ilp_add_var",      "add a variable to ILP model",               ("ilp", "str"),            "ilp", cost=1)
register("ilp_add_constraint","add a constraint to ILP model",            ("ilp", "str"),            "ilp", cost=2)
register("ilp_set_objective","set the objective function",                ("ilp", "str"),            "ilp", cost=2)
register("ilp_solve",        "solve the ILP model",                       ("ilp",),                  "schedule", cost=30)

# --- Analysis atoms ---
register("analyze_critical", "find critical path in schedule",            ("schedule",),             "critical_path", cost=5)
register("analyze_mobility", "compute operation mobility (slack)",        ("schedule",),             "schedule", cost=5)
register("analyze_dep_type", "classify all edges in graph as data/control/mem", ("graph",),          "graph", cost=3)

# --- Literal atoms (produce raw values for other atoms to consume) ---
register("lit_str",          "literal string value",                      ("str",),                  "str", cost=0)
register("lit_int",          "literal integer value",                     ("int",),                  "int", cost=0)
register("node_new",         "create a node descriptor",                  ("str", "str"),            "str", cost=1)
register("str_fmt",          "format a string from template + values",    ("str",),                  "str", cost=1)


# ============================================================
# Query helpers
# ============================================================

def get_atom(opcode: str) -> AtomSig:
    """Get an atom's signature by opcode."""
    if opcode not in ATOMS:
        raise KeyError(f"Unknown atom opcode: {opcode}")
    return ATOMS[opcode]

def atoms_by_output(output_type: str) -> list[AtomSig]:
    """Find all atoms that produce a given output type."""
    return [a for a in ATOMS.values() if a.output_type == output_type]

def atoms_by_input(input_type: str) -> list[AtomSig]:
    """Find all atoms that consume a given input type."""
    return [a for a in ATOMS.values() if input_type in a.input_types]

def list_atoms() -> list[str]:
    """List all registered atom opcodes."""
    return sorted(ATOMS.keys())

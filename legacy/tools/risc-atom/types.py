"""
Core data types for the RISC atom space.
Every atom operates on these types — no side effects, no global state.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class PortDir(Enum):
    INPUT = auto()
    OUTPUT = auto()
    INOUT = auto()


class EdgeKind(Enum):
    DATA = auto()        # data dependency (result flows from A to B)
    CONTROL = auto()     # control dependency (A must happen before B)
    MEMORY = auto()      # memory ordering dependency
    CONDITION = auto()   # conditional branch


@dataclass(frozen=True)
class Signal:
    """A named wire/register with known width and signedness."""
    name: str
    width: int
    signed: bool = False


@dataclass(frozen=True)
class Node:
    """A node in a graph (CDFG operation, FSM state, etc.)"""
    id: str
    kind: str            # "op", "state", "phi", "const", "io"
    opcode: str = ""     # e.g. "add", "mul", "cmp", "load", "store"
    latency: int = 1     # clock cycles this operation takes


@dataclass(frozen=True)
class Edge:
    """A directed edge between two nodes."""
    src: str
    dst: str
    kind: EdgeKind = EdgeKind.DATA
    port: int = 0        # which output/input port index


@dataclass(frozen=True)
class Graph:
    """An immutable graph of nodes and edges."""
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()

    def add_node(self, node: Node) -> "Graph":
        return Graph(self.nodes + (node,), self.edges)

    def add_edge(self, edge: Edge) -> "Graph":
        return Graph(self.nodes, self.edges + (edge,))

    def remove_node(self, node_id: str) -> "Graph":
        return Graph(
            tuple(n for n in self.nodes if n.id != node_id),
            tuple(e for e in self.edges if e.src != node_id and e.dst != node_id)
        )


@dataclass(frozen=True)
class Port:
    name: str
    direction: PortDir
    signal: Signal


@dataclass(frozen=True)
class Assignment:
    lhs: str
    rhs: str

@dataclass(frozen=True)
class AlwaysBlock:
    sensitivity: str           # "posedge clk or negedge rst_n"
    body: str

@dataclass(frozen=True)
class Instance:
    name: str
    module_type: str
    connections: tuple[tuple[str, str], ...]  # (port, signal) pairs


@dataclass(frozen=True)
class Module:
    """A hardware module under construction."""
    name: str
    ports: tuple[Port, ...] = ()
    assigns: tuple[Assignment, ...] = ()
    always_blocks: tuple[AlwaysBlock, ...] = ()
    instances: tuple[Instance, ...] = ()

    def add_port(self, port: Port) -> "Module":
        return Module(self.name, self.ports + (port,),
                      self.assigns, self.always_blocks, self.instances)

    def add_assign(self, a: Assignment) -> "Module":
        return Module(self.name, self.ports,
                      self.assigns + (a,), self.always_blocks, self.instances)

    def add_always(self, ab: AlwaysBlock) -> "Module":
        return Module(self.name, self.ports,
                      self.assigns, self.always_blocks + (ab,), self.instances)

    def add_instance(self, inst: Instance) -> "Module":
        return Module(self.name, self.ports,
                      self.assigns, self.always_blocks, self.instances + (inst,))


@dataclass(frozen=True)
class Schedule:
    """Maps each node in a CDFG to a clock cycle."""
    mapping: tuple[tuple[str, int], ...] = ()  # (node_id, cycle)
    ii: int = 1  # initiation interval (for pipelined loops)

    def assign(self, node_id: str, cycle: int) -> "Schedule":
        return Schedule(
            tuple((n, c) for n, c in self.mapping if n != node_id) + ((node_id, cycle),),
            self.ii
        )

    def cycle_of(self, node_id: str) -> Optional[int]:
        for n, c in self.mapping:
            if n == node_id:
                return c
        return None


@dataclass(frozen=True)
class ILPModel:
    """An integer linear programming model."""
    name: str
    vars: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    objective: str = "minimize: 0"

    def add_var(self, name: str) -> "ILPModel":
        return ILPModel(self.name, self.vars + (name,),
                        self.constraints, self.objective)

    def add_constraint(self, expr: str) -> "ILPModel":
        return ILPModel(self.name, self.vars,
                        self.constraints + (expr,), self.objective)

    def set_objective(self, expr: str) -> "ILPModel":
        return ILPModel(self.name, self.vars, self.constraints, expr)


@dataclass(frozen=True)
class TopoList:
    """Topologically sorted list of node IDs."""
    node_ids: tuple[str, ...]
    graph_ref: str = ""    # reference to which graph was sorted


@dataclass(frozen=True)
class CriticalPath:
    """Critical path analysis result."""
    path: tuple[str, ...]  # ordered node IDs on the critical path
    length: int            # total latency


# Union type for any atom output
AtomValue = Graph | Signal | Module | Schedule | ILPModel | TopoList | CriticalPath | str | int | tuple

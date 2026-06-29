"""
Dependency graph for atom sequences.
Tracks which atoms depend on which outputs, enables ready-set computation.
"""

from dataclasses import dataclass, field
from collections import deque

from .decomposer import AtomCall, AtomSequence


@dataclass
class DepNode:
    """A node in the atom dependency graph."""
    call: AtomCall
    producers: set[str]    # label names (without $) for ref inputs
    consumers: set[str]    # labels that depend on this output
    ready: bool = False


@dataclass
class DepGraph:
    """Dependency graph of an atom sequence."""
    nodes: dict[str, DepNode] = field(default_factory=dict)  # output label → node
    available: set[str] = field(default_factory=set)          # currently available labels (produced or input)

    def build(self, seq: AtomSequence) -> "DepGraph":
        # Phase 1: create nodes
        for call in seq.calls:
            self.nodes[call.output] = DepNode(
                call=call,
                producers=set(call.ref_inputs()),
                consumers=set()
            )

        # Phase 2: wire consumers
        for call in seq.calls:
            for in_label in call.ref_inputs():
                if in_label in self.nodes:
                    self.nodes[in_label].consumers.add(call.output)

        # Phase 3: mark external inputs as available
        for label in seq.input_labels:
            self.available.add(label)

        # Phase 4: compute initial ready set
        self._update_ready()

        return self

    def _update_ready(self):
        for label, node in self.nodes.items():
            if not node.ready:
                node.ready = all(p in self.available for p in node.producers)

    def ready_set(self) -> set[str]:
        return {label for label, node in self.nodes.items() if node.ready}

    def execute(self, label: str) -> set[str]:
        if label not in self.nodes:
            raise KeyError(f"Unknown atom label: {label}")
        node = self.nodes[label]
        node.ready = False
        self.available.add(label)

        newly_ready = set()
        for consumer_label in node.consumers:
            if consumer_label in self.nodes:
                consumer = self.nodes[consumer_label]
                if not consumer.ready:
                    consumer.ready = all(p in self.available for p in consumer.producers)
                    if consumer.ready:
                        newly_ready.add(consumer_label)

        return newly_ready

    def topological_order(self) -> list[str]:
        atom_in_degree: dict[str, int] = {}
        atom_adj: dict[str, list[str]] = {}
        for label, node in self.nodes.items():
            # Only count deps from other atoms (labels in self.nodes)
            atom_in_degree[label] = sum(1 for p in node.producers if p in self.nodes)
            for p in node.producers:
                if p in self.nodes:
                    atom_adj.setdefault(p, []).append(label)

        queue = deque(l for l, d in atom_in_degree.items() if d == 0)
        order = []
        while queue:
            cur = queue.popleft()
            order.append(cur)
            for nxt in atom_adj.get(cur, []):
                atom_in_degree[nxt] -= 1
                if atom_in_degree[nxt] == 0:
                    queue.append(nxt)

        return order

    def dump(self) -> str:
        lines = []
        topo = self.topological_order()
        for label in topo:
            node = self.nodes[label]
            ready_mark = "✓" if node.ready else " "
            prods = ", ".join(sorted(node.producers)) if node.producers else "—"
            cons = ", ".join(sorted(node.consumers)) if node.consumers else "—"
            lines.append(
                f"  [{ready_mark}] {label:<25}"
                f"  ← [{prods:<25}]"
                f"  → [{cons}]"
            )
        return "\n".join(lines)


def build_dep_graph(seq: AtomSequence) -> DepGraph:
    """Convenience: build and return a dependency graph."""
    return DepGraph().build(seq)

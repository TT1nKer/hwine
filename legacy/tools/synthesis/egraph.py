"""
E-graph engine for gate-level circuit optimization.
Key concepts:
  - EClass: equivalence class of ENodes (all represent the same value)
  - ENode: a gate operation with children referencing e-class IDs
  - Union: merging two e-classes (they are equivalent)
  - Congruence closure: if children are in same e-classes, parents should be too
  - Saturation: apply rewrite rules until no new equivalences found
  - Worklist-driven: only match patterns on recently changed e-classes and
    their neighbors, avoiding O(n) full scans per rule.
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from collections import deque

from .gate_ir import Op, GateNode


@dataclass(order=True, frozen=True)
class ENode:
    """An e-node: op + list of e-class IDs for children."""
    op: Op
    children: tuple  # tuple of e-class IDs (int)

    def __repr__(self):
        return f"{self.op.name}({','.join(map(str, self.children))})"


@dataclass
class EClass:
    """An equivalence class of ENodes."""
    id: int
    nodes: set[ENode] = field(default_factory=set)


class EGraph:
    """E-graph for gate-level circuit optimization."""

    def __init__(self):
        self.classes: dict[int, EClass] = {}
        self.parents: list[int] = []       # union-find parent array
        self.hashcons: dict[ENode, int] = {}
        self.next_id = 0

        # Worklist-driven + op-type indexed pattern matching
        self.changed: set[int] = set()
        self.parents_of: dict[int, set[int]] = {}
        # by_op[Op] = set of e-class ids that contain at least one node of that op
        self.by_op: dict[Op, set[int]] = {}

    def _add_to_op_index(self, cid: int, node: ENode):
        self.by_op.setdefault(node.op, set()).add(self.find(cid))

    def _remove_from_op_index(self, cid: int, node: ENode):
        idx = self.by_op.get(node.op)
        if idx:
            idx.discard(self.find(cid))

    def make_class(self) -> int:
        cid = self.next_id
        self.next_id += 1
        self.classes[cid] = EClass(cid)
        self.parents.append(cid)
        while len(self.parents) <= cid:
            self.parents.append(len(self.parents))
        self.changed.add(cid)
        return cid

    def find(self, cid: int) -> int:
        while self.parents[cid] != cid:
            self.parents[cid] = self.parents[self.parents[cid]]
            cid = self.parents[cid]
        return cid

    def union(self, a: int, b: int) -> int:
        """Merge e-class b into a. Returns the canonical id."""
        a = self.find(a)
        b = self.find(b)
        if a == b:
            return a
        self.parents[b] = a
        merged = self.classes[b]
        self.classes[a].nodes.update(merged.nodes)
        self.changed.add(a)
        # Merge op indices
        for node in merged.nodes:
            self.by_op.setdefault(node.op, set()).discard(b)
            self.by_op.setdefault(node.op, set()).add(a)
        # Transfer parent tracking
        if b in self.parents_of:
            for p in self.parents_of.pop(b, set()):
                self.parents_of.setdefault(a, set()).add(p)
        del self.classes[b]
        # Only re-check parents of the merged classes
        needs_recheck = self.parents_of.get(a, set()).copy()
        for parent_cid in needs_recheck:
            parent_cid = self.find(parent_cid)
            if parent_cid not in self.classes or parent_cid == a:
                continue
            for node in list(self.classes[parent_cid].nodes):
                new_children = tuple(self.find(c) for c in node.children)
                if new_children != node.children:
                    self.classes[parent_cid].nodes.discard(node)
                    self.classes[parent_cid].nodes.add(ENode(node.op, new_children))
                    self.hashcons.pop(ENode(node.op, node.children), None)
                    self.hashcons[ENode(node.op, new_children)] = parent_cid
                    self.changed.add(parent_cid)
        return a

    def _register_parent(self, child_cid: int, parent_cid: int):
        """Track that parent_cid depends on child_cid."""
        self.parents_of.setdefault(self.find(child_cid), set()).add(parent_cid)

    def add(self, node: ENode) -> int:
        canon_children = tuple(self.find(c) for c in node.children)
        canon_node = ENode(node.op, canon_children)

        if canon_node in self.hashcons:
            return self.find(self.hashcons[canon_node])

        cid = self.make_class()
        self.classes[cid].nodes.add(canon_node)
        self.hashcons[canon_node] = cid
        self.by_op.setdefault(canon_node.op, set()).add(cid)

        for child in canon_node.children:
            self._register_parent(child, cid)

        for existing_cid, ecls in list(self.classes.items()):
            if existing_cid == cid:
                continue
            existing_cid = self.find(existing_cid)
            if existing_cid == cid:
                continue
            for en in list(ecls.nodes):
                if en == canon_node:
                    self.union(cid, existing_cid)
                    return self.find(cid)

        return cid

    def rebuild(self):
        """Repair the e-graph: canonicalize children of all changed nodes."""
        to_fix = set(self.changed)
        while to_fix:
            current = to_fix.copy()
            to_fix.clear()
            for cid in current:
                cid = self.find(cid)
                if cid not in self.classes:
                    continue
                ecls = self.classes[cid]
                for node in list(ecls.nodes):
                    new_children = tuple(self.find(c) for c in node.children)
                    if new_children != node.children:
                        ecls.nodes.discard(node)
                        ecls.nodes.add(ENode(node.op, new_children))
                        to_fix.add(cid)

    def ematch(self, pattern_fn: Callable[[ENode], bool]) -> list[tuple[int, ENode]]:
        """Worklist-driven + op-indexed pattern matching.
        Only scans e-classes in the transitive fan-out of recently changed nodes
        (those that reference changed nodes as children).
        For simple op-type queries (n.op == Op.X), uses op index for O(|X_nodes|)."""
        to_scan = set()
        for cid in self.changed:
            cid = self.find(cid)
            to_scan.add(cid)
            # Walk up: any parent that references a changed child should be re-scanned
            work = deque([cid])
            while work:
                cur = work.popleft()
                for parent_cid in self.parents_of.get(cur, set()):
                    parent_cid = self.find(parent_cid)
                    if parent_cid not in to_scan and parent_cid in self.classes:
                        to_scan.add(parent_cid)
                        work.append(parent_cid)

        matched = []
        for cid in to_scan:
            if cid not in self.classes:
                continue
            for node in list(self.classes[cid].nodes):
                if pattern_fn(node):
                    matched.append((cid, node))
        return matched

    def clear_changed(self):
        self.changed.clear()

    def apply_rule(self, name: str, pattern_fn, apply_fn):
        matches = self.ematch(pattern_fn)
        for cid, node in matches:
            apply_fn(self, self.find(cid), node)

    def dump(self, max_nodes: int = 20) -> str:
        lines = [f"EGraph: {len(self.classes)} classes"]
        count = 0
        for cid in sorted(self.classes.keys()):
            cid = self.find(cid)
            if cid not in self.classes:
                continue
            ecls = self.classes[cid]
            nodes_str = ", ".join(str(n) for n in list(ecls.nodes)[:3])
            more = "..." if len(ecls.nodes) > 3 else ""
            lines.append(f"  C{cid}: [{nodes_str}{more}]")
            count += 1
            if count >= max_nodes:
                lines.append(f"  ... ({len(self.classes) - max_nodes} more)")
                break
        return "\n".join(lines)

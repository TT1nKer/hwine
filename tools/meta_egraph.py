"""
E-graph engine for meta-operation rewriting with FPGA-aware extraction.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Callable, Optional

from .meta_ir import ENode, AtomOp, fpga_cost_fn, FPGA_DELAY_NS, FPGA_LUT_COST, FPGA_DSP_COST, FPGA_FF_COST, FPGA_CYC_LATENCY


@dataclass
class EClass:
    id: int
    nodes: set[ENode] = field(default_factory=set)


class EGraph:
    def __init__(self):
        self.classes: dict[int, EClass] = {}
        self.parents: list[int] = []
        self.hashcons: dict[ENode, int] = {}
        self.next_id = 0
        self.changed: set[int] = set()
        self.parents_of: dict[int, set[int]] = {}
        self.by_op: dict[AtomOp, set[int]] = {}
        self.union_count = 0
        self.match_count = 0

    def _canon(self, cid: int) -> int:
        while self.parents[cid] != cid:
            self.parents[cid] = self.parents[self.parents[cid]]
            cid = self.parents[cid]
        return cid

    def _fresh_class(self) -> int:
        cid = self.next_id
        self.next_id += 1
        self.classes[cid] = EClass(cid)
        while len(self.parents) <= cid:
            self.parents.append(len(self.parents))
        self.changed.add(cid)
        return cid

    def _is_valid_cid(self, c) -> bool:
        return isinstance(c, int) and 0 <= c < self.next_id and c < len(self.parents)

    def _wrap_child(self, c) -> int:
        """Ensure a child is an e-class ID. Wraps strings/ints as literal e-classes."""
        if self._is_valid_cid(c):
            return c
        if isinstance(c, str):
            return self.add(ENode(AtomOp.STR_LIT, (), c))
        if isinstance(c, (int, float)) and not self._is_valid_cid(c):
            return self.add(ENode(AtomOp.CONST, (), c))  # meta=c
        return c
        if isinstance(c, str):
            h = abs(hash(c)) % 0x7FFFFFFF
            if h in self.classes:
                return self._canon(h)
            return self.add(ENode(AtomOp.STR_LIT, (), c))
        if isinstance(c, (int, float)) and not self._is_valid_cid(c):
            return self.add(ENode(AtomOp.CONST, (int(c),)))
        return c

    def add(self, node: ENode) -> int:
        wrapped = tuple(self._wrap_child(c) for c in node.children)
        return self._add_raw(ENode(node.op, wrapped, node.meta))

    def _add_raw(self, node: ENode) -> int:
        canon_children = tuple(self._canon(c) for c in node.children)
        canon_node = ENode(node.op, canon_children, node.meta)
        if canon_node in self.hashcons:
            return self._canon(self.hashcons[canon_node])
        cid = self._fresh_class()
        self.classes[cid].nodes.add(canon_node)
        self.hashcons[canon_node] = cid
        self.by_op.setdefault(canon_node.op, set()).add(cid)
        for child in canon_children:
            self.parents_of.setdefault(child, set()).add(cid)
        for other_cid, ecls in list(self.classes.items()):
            if other_cid == cid:
                continue
            other_cid = self._canon(other_cid)
            if other_cid == cid:
                continue
            for en in list(ecls.nodes):
                if en == canon_node:
                    self._union(cid, other_cid)
                    return self._canon(cid)
        return cid

    def _union(self, a: int, b: int) -> int:
        a = self._canon(a); b = self._canon(b)
        if a == b:
            return a
        self.parents[b] = a
        self.union_count += 1
        merged = self.classes[b]
        self.classes[a].nodes.update(merged.nodes)
        self.changed.add(a)
        for node in merged.nodes:
            self.by_op.get(node.op, set()).discard(b)
            self.by_op.setdefault(node.op, set()).add(a)
        if b in self.parents_of:
            for p in self.parents_of.pop(b, set()):
                self.parents_of.setdefault(a, set()).add(p)
        del self.classes[b]
        self._repair_parents(a)
        return a

    def _repair_parents(self, cid: int):
        to_repair = self.parents_of.get(cid, set()).copy()
        for parent_cid in to_repair:
            parent_cid = self._canon(parent_cid)
            if parent_cid not in self.classes or parent_cid == cid:
                continue
            for node in list(self.classes[parent_cid].nodes):
                new_children = tuple(self._canon(c) for c in node.children)
                if new_children != node.children:
                    self.classes[parent_cid].nodes.discard(node)
                    new_node = ENode(node.op, new_children, node.meta)
                    self.classes[parent_cid].nodes.add(new_node)
                    self.hashcons.pop(ENode(node.op, node.children, node.meta), None)
                    self.hashcons[new_node] = parent_cid
                    self.changed.add(parent_cid)

    def rebuild(self):
        for cid in list(self.classes.keys()):
            cid = self._canon(cid)
            if cid not in self.classes:
                continue
            for node in list(self.classes[cid].nodes):
                new_children = tuple(self._canon(c) for c in node.children)
                if new_children != node.children:
                    self.classes[cid].nodes.discard(node)
                    self.classes[cid].nodes.add(ENode(node.op, new_children, node.meta))

    def ematch(self, pattern_fn, op_filter: Optional[AtomOp] = None) -> list[tuple[int, ENode]]:
        to_scan = set()
        for cid in self.changed:
            cid = self._canon(cid)
            to_scan.add(cid)
            work = deque([cid])
            while work:
                cur = work.popleft()
                for parent_cid in self.parents_of.get(cur, set()):
                    parent_cid = self._canon(parent_cid)
                    if parent_cid not in to_scan and parent_cid in self.classes:
                        to_scan.add(parent_cid)
                        work.append(parent_cid)
        if op_filter and op_filter in self.by_op:
            to_scan = to_scan & self.by_op[op_filter]
        matched = []
        for cid in to_scan:
            if cid not in self.classes:
                continue
            for node in list(self.classes[cid].nodes):
                if pattern_fn(node, cid):
                    matched.append((cid, node))
        self.match_count += len(matched)
        return matched

    def clear_changed(self):
        self.changed.clear()

    def saturate(self, rules: list, max_iter: int = 30, max_classes: int = 5000) -> int:
        for i in range(max_iter):
            if len(self.classes) > max_classes:
                return i
            snapshot = self.changed.copy()
            for rule in rules:
                rule(self)
            self.rebuild()
            self.changed -= snapshot
            if not self.changed:
                return i + 1
        return max_iter

    # ─── FPGA-Aware Extraction ────────────────────────────────

    def extract_fpga_optimal(self, cid: int, weight_delay: float = 2.0
                             ) -> tuple[ENode, dict]:
        cid = self._canon(cid)
        memo = {}
        visiting = set()  # cycle detection

        def best(c: int) -> tuple[ENode, dict]:
            c = self._canon(c)
            if c in memo:
                return memo[c]
            if c in visiting:
                return (None, {'lut': 0, 'dsp': 0, 'ff': 0, 'bram': 0,
                               'delay_ns': 0, 'cycles': 0, 'score': 0})
            if c not in self.classes:
                memo[c] = (None, {'lut': 0, 'dsp': 0, 'ff': 0, 'bram': 0,
                                   'delay_ns': 0, 'cycles': 0, 'score': 0})
                return memo[c]
            visiting.add(c)
            ecls = self.classes[c]
            best_node, best_stats = None, None
            best_score = float('inf')
            for node in ecls.nodes:
                child_results = [best(ch) for ch in node.children]
                child_luts = sum(r[1]['lut'] for r in child_results)
                child_dsps = sum(r[1]['dsp'] for r in child_results)
                child_ffs  = sum(r[1]['ff'] for r in child_results)
                child_delay = max((r[1]['delay_ns'] for r in child_results), default=0)
                child_cycles = max((r[1].get('cycles', 0) for r in child_results), default=0)

                lut   = FPGA_LUT_COST.get(node.op, 0) + child_luts
                dsp   = FPGA_DSP_COST.get(node.op, 0) + child_dsps
                ff    = FPGA_FF_COST.get(node.op, 0) + child_ffs
                delay = FPGA_DELAY_NS.get(node.op, 0) + child_delay
                cycle_lat = FPGA_CYC_LATENCY.get(node.op, 0) + child_cycles

                score = lut + dsp * 8 + ff * 0.02 + delay * weight_delay

                if score < best_score:
                    best_score = score
                    best_node = node
                    best_stats = {'lut': lut, 'dsp': dsp, 'ff': ff, 'delay_ns': delay,
                                  'cycles': cycle_lat, 'score': best_score}
            visiting.discard(c)
            memo[c] = (best_node, best_stats)
            return memo[c]

        result = best(cid)
        stats = result[1]
        if stats:
            stats['fmax_mhz'] = min(1000.0/stats['delay_ns'] if stats['delay_ns']>0 else 500, 500)
            stats['lut_depth'] = 2  # rough estimate
        return result

    def extract_pareto_front(self, cid: int, sample: int = 50) -> list[dict]:
        """Enumerate Pareto-optimal points from the e-class.
        Each point: {node, lut, dsp, ff, delay_ns, fmax_mhz, cycles}."""
        cid = self._canon(cid)
        ecls = self.classes[cid]
        points = []

        # Sample the largest nodes in the e-class
        sampled = sorted(ecls.nodes, key=lambda n: -len(str(n)))[:sample]

        for node in sampled:
            # Do a greedy extraction for this node (one path)
            stats = self._extract_node_stats(node, set())
            if stats:
                points.append(stats)

        # Pareto filter: non-dominated in (area≈lut+dsp*10, delay_ns)
        pareto = []
        for p in points:
            area = p['lut'] + p['dsp'] * 10 + p['ff'] * 0.02
            delay = p['delay_ns']
            dominated = False
            for other in points:
                a2 = other['lut'] + other['dsp'] * 10 + other['ff'] * 0.02
                d2 = other['delay_ns']
                if (a2 <= area and d2 <= delay and (a2 < area or d2 < delay)):
                    dominated = True
                    break
            if not dominated:
                pareto.append(p)

        pareto.sort(key=lambda p: p['delay_ns'])
        return pareto

    def _extract_node_stats(self, node: ENode, visited: set) -> Optional[dict]:
        """Recursively compute stats for a specific node (greedy, one path)."""
        if id(node) in visited:
            return None
        visited.add(id(node))

        child_luts = 0; child_dsps = 0; child_ffs = 0; child_delay = 0; child_cycles = 0
        for ch in node.children:
            ch = self._canon(ch)
            if ch in self.classes and self.classes[ch].nodes:
                # Pick cheapest child node (greedy)
                best_n = min(self.classes[ch].nodes,
                             key=lambda n: FPGA_LUT_COST.get(n.op, 0) + FPGA_DSP_COST.get(n.op, 0)*8)
                sub = self._extract_node_stats(best_n, visited)
                if sub:
                    child_luts += sub['lut']
                    child_dsps += sub['dsp']
                    child_ffs  += sub['ff']
                    child_delay = max(child_delay, sub['delay_ns'])
                    child_cycles = max(child_cycles, sub['cycles'])

        delay = FPGA_DELAY_NS.get(node.op, 0) + child_delay
        return {
            'node': node, 'repr': str(node),
            'lut': FPGA_LUT_COST.get(node.op, 0) + child_luts,
            'dsp': FPGA_DSP_COST.get(node.op, 0) + child_dsps,
            'ff': FPGA_FF_COST.get(node.op, 0) + child_ffs,
            'delay_ns': delay,
            'fmax_mhz': min(1000.0 / delay if delay > 0 else 500, 500),
            'cycles': FPGA_CYC_LATENCY.get(node.op, 0) + child_cycles,
        }

    # ─── Legacy extraction (backward compat) ──────────────────

    def extract_optimal(self, cid: int, cost_fn=None) -> tuple[ENode, float]:
        cid = self._canon(cid)
        memo = {}
        def best(c):
            if c in memo:
                return memo[c]
            ecls = self.classes[c]
            best_node, best_cost = None, float('inf')
            for node in ecls.nodes:
                total = sum(best(ch)[1] for ch in node.children)
                total += 1 if cost_fn is None else cost_fn(node)
                if total < best_cost:
                    best_cost = total
                    best_node = node
            memo[c] = (best_node, best_cost)
            return memo[c]
        return best(cid)

    def extract_depth(self, cid: int) -> tuple[ENode, float]:
        cid = self._canon(cid)
        memo = {}
        def best(c):
            if c in memo:
                return memo[c]
            ecls = self.classes[c]
            best_node, best_depth = None, float('inf')
            for node in ecls.nodes:
                child_depths = [best(ch)[1] for ch in node.children] if node.children else [0]
                depth = FPGA_DELAY_NS.get(node.op, 1) + max(child_depths)
                if depth < best_depth:
                    best_depth = depth
                    best_node = node
            memo[c] = (best_node, best_depth)
            return memo[c]
        return best(cid)

    # ─── Debug ────────────────────────────────────────────────

    def dump(self, max_nodes: int = 30) -> str:
        lines = [f"EGraph: {len(self.classes)} classes, {self.union_count} unions"]
        count = 0
        for cid in sorted(self.classes.keys()):
            cid = self._canon(cid)
            if cid not in self.classes:
                continue
            ecls = self.classes[cid]
            ns = ", ".join(str(n) for n in list(ecls.nodes)[:3])
            more = f" +{len(ecls.nodes)-3}" if len(ecls.nodes) > 3 else ""
            lines.append(f"  C{cid}: [{ns}{more}]")
            count += 1
            if count >= max_nodes:
                lines.append(f"  ... ({len(self.classes) - max_nodes} more)")
                break
        return "\n".join(lines)


def count_lut_depth(node: ENode, eclass_id: int = 0) -> int:
    """Count LUT-delay ops on the longest path (ignoring DSP and wiring)."""
    if node.op in (AtomOp.ADD, AtomOp.REDUCE_ADD, AtomOp.SAT, AtomOp.ROUND, AtomOp.SCAN):
        return 1
    return 0

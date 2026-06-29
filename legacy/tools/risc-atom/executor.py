"""
Atom executor: runs an atom sequence against real implementations.
For now, stubs validate the pipeline; full implementations TBD.
"""

from .decomposer import AtomCall, AtomSequence, is_ref, ref
from .dep_graph import build_dep_graph
from .registry import get_atom


class Executor:
    def __init__(self):
        self.values: dict[str, object] = {}
        self.executed: set[str] = set()

    def run(self, seq: AtomSequence) -> dict[str, object]:
        dep_graph = build_dep_graph(seq)
        order = dep_graph.topological_order()

        for label in seq.input_labels:
            self.values[label] = f"<external:{label}>"

        for label in order:
            self._exec_one(dep_graph.nodes[label].call)

        return {out: self.values.get(out) for out in seq.output_labels}

    def _exec_one(self, call: AtomCall):
        if call.output in self.executed:
            return
        inputs = [self._resolve(i) for i in call.inputs]
        self.values[call.output] = f"<{call.opcode}({', '.join(str(x) for x in inputs)})>"
        self.executed.add(call.output)

    def _resolve(self, inp) -> object:
        s = str(inp)
        if is_ref(s):
            return self.values.get(s[1:], f"<null:{s[1:]}>")
        return inp

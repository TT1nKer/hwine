"""
Task Decomposer: takes a high-level task (as a structured description)
and decomposes it into a sequence of RISC atom invocations.

Each AtomCall is immutable: opcode + inputs + output label.
Inputs can be:
  - label refs:   "$label"  → references output of another atom
  - literals:       "hello" → inline string value
                    42      → inline integer value
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .registry import ATOMS, get_atom
from .types import AtomValue


def is_ref(s: str) -> bool:
    """Check if a string input is a label reference."""
    return s.startswith("$")

def ref(label: str) -> str:
    """Create a label reference string."""
    return f"${label}"

def label_refs(inputs: tuple) -> set[str]:
    """Extract label names from all ref-type inputs."""
    refs = set()
    for inp in inputs:
        s = str(inp)
        if is_ref(s):
            refs.add(s[1:])
    return refs


@dataclass(frozen=True)
class AtomCall:
    """One invocation of an atom."""
    opcode: str
    inputs: tuple          # Union[str, int] — refs are "$label", everything else is a literal
    output: str            # label for this call's output
    meta: str = ""         # human-readable annotation

    def ref_inputs(self) -> list[str]:
        """Return the label names (without $ prefix) of all ref-type inputs."""
        return [str(i)[1:] for i in self.inputs if is_ref(str(i))]

    def to_dict(self) -> dict:
        return {
            "opcode": self.opcode,
            "inputs": list(self.inputs),
            "output": self.output,
            "meta": self.meta
        }

    @staticmethod
    def from_dict(d: dict) -> "AtomCall":
        return AtomCall(d["opcode"], tuple(d["inputs"]), d["output"], d.get("meta", ""))


@dataclass
class AtomSequence:
    """An ordered sequence of atom calls forming a hardware design task."""
    calls: list[AtomCall] = field(default_factory=list)
    input_labels: set[str] = field(default_factory=set)   # labels provided externally
    output_labels: set[str] = field(default_factory=set)  # labels we want as final output

    def add(self, opcode: str, inputs: list, output: str, meta: str = "") -> "AtomSequence":
        """Add an atom call. inputs: mix of "$label" (refs) and raw str/int (literals)."""
        sig = get_atom(opcode)

        if len(inputs) != len(sig.input_types):
            raise ValueError(
                f"{opcode} expects {len(sig.input_types)} inputs, got {len(inputs)}: {sig.input_types}"
            )

        self.calls.append(AtomCall(opcode, tuple(inputs), output, meta))
        return self

    def mark_input(self, label: str):
        self.input_labels.add(label)

    def mark_output(self, label: str):
        self.output_labels.add(label)

    def to_dict(self) -> dict:
        return {
            "calls": [c.to_dict() for c in self.calls],
            "input_labels": sorted(self.input_labels),
            "output_labels": sorted(self.output_labels)
        }

    @staticmethod
    def from_dict(d: dict) -> "AtomSequence":
        seq = AtomSequence()
        seq.calls = [AtomCall.from_dict(c) for c in d["calls"]]
        seq.input_labels = set(d.get("input_labels", []))
        seq.output_labels = set(d.get("output_labels", []))
        return seq

    def dump(self) -> str:
        lines = []
        width = max((len(c.output) for c in self.calls), default=10)
        for c in self.calls:
            in_str = ", ".join(str(i) for i in c.inputs) if c.inputs else "()"
            meta = f"  # {c.meta}" if c.meta else ""
            lines.append(f"  {c.output:<{width}} = {c.opcode}({in_str}){meta}")
        return "\n".join(lines)

    def __len__(self):
        return len(self.calls)


# ============================================================
# Task decomposer: generates AtomSequences from task specs
# ============================================================

class TaskDecomposer:
    """Decompose high-level hardware design tasks into RISC atom sequences."""

    def __init__(self):
        self._counter = 0

    def _label(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    # ---------- graph building ----------

    def decompose_build_cdfg(self, operations: list[dict]) -> AtomSequence:
        """
        Build a CDFG from a list of operations.
        Each operation: {"id": str, "opcode": str, "predecessors": [str], "latency": int}
        """
        seq = AtomSequence()
        g = self._label("g")

        seq.add("graph_new", [], g, "create empty CDFG")

        # Add nodes
        node_labels = {}
        for op in operations:
            nid = op["id"]
            opcode = op.get("opcode", "unknown")
            seq.add("graph_add_node", [ref(g), nid, opcode], g := self._label("g"),
                    f"add node {nid}")
            node_labels[nid] = nid

        # Add edges (nid values are used as string literals, not refs)
        for op in operations:
            for pred in op.get("predecessors", []):
                seq.add("graph_add_edge", [ref(g), pred, op["id"]],
                        g := self._label("g"),
                        f"add edge {pred} → {op['id']}")

        seq.mark_output(g)
        return seq

    # ---------- scheduling ----------

    def decompose_schedule(self, cdfg_label: str) -> AtomSequence:
        seq = AtomSequence()
        seq.mark_input(cdfg_label)

        seq.add("sched_asap", [ref(cdfg_label)], asap := self._label("sched"), "ASAP scheduling")
        seq.add("sched_alap", [ref(cdfg_label), 10], alap := self._label("sched"),
                "ALAP scheduling (budget 10)")
        seq.add("analyze_mobility", [ref(asap)], mob := self._label("sched"),
                "compute operation mobility")

        seq.mark_output(mob)
        return seq

    def decompose_list_schedule(self, cdfg_label: str, num_resources: int) -> AtomSequence:
        seq = AtomSequence()
        seq.mark_input(cdfg_label)

        seq.add("sched_list", [ref(cdfg_label), num_resources], sched := self._label("sched"),
                f"list scheduling with {num_resources} resources")

        seq.mark_output(sched)
        return seq

    def decompose_critical_path(self, schedule_label: str) -> AtomSequence:
        seq = AtomSequence()
        seq.mark_input(schedule_label)
        seq.add("analyze_critical", [ref(schedule_label)], cp := self._label("cp"),
                "find critical path")
        seq.mark_output(cp)
        return seq

    def decompose_rtl_emit(self, module_label: str) -> AtomSequence:
        seq = AtomSequence()
        seq.mark_input(module_label)
        seq.add("module_emit", [ref(module_label)], verilog := self._label("verilog"),
                "emit synthesizable Verilog")
        seq.mark_output(verilog)
        return seq

    # ---------- full pipeline ----------

    def decompose_full_pipeline(self, operations: list[dict],
                                 num_resources: int = 2) -> AtomSequence:
        cdfg_seq = self.decompose_build_cdfg(operations)
        cdfg_out = cdfg_seq.output_labels.pop()
        sched_seq = self.decompose_schedule(cdfg_out)
        sched_out = sched_seq.output_labels.pop()
        list_seq = self.decompose_list_schedule(cdfg_out, num_resources)
        list_out = list_seq.output_labels.pop()
        cp_seq = self.decompose_critical_path(sched_out)
        cp_out = cp_seq.output_labels.pop()

        merged = AtomSequence()
        label_map: dict[str, str] = {}

        def merge(sub: AtomSequence, prefix: str):
            for call in sub.calls:
                # Remap ref inputs
                new_in = []
                for inp in call.inputs:
                    s = str(inp)
                    if is_ref(s):
                        old_label = s[1:]
                        new_label = label_map.get(old_label, f"{prefix}_{old_label}")
                        new_in.append(ref(new_label))
                    else:
                        new_in.append(inp)
                new_out = f"{prefix}_{call.output}"
                label_map[call.output] = new_out
                merged.add(call.opcode, new_in, new_out, call.meta)

        merge(cdfg_seq, "cdfg")
        merge(sched_seq, "sched")
        merge(list_seq, "list")
        merge(cp_seq, "cp")

        merged.mark_output(label_map.get(cp_out, cp_out))
        return merged

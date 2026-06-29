"""
Validator: checks that an atom sequence is well-formed and complete.

Rules:
  1. Every input label is either a) produced by a previous atom, or b) marked as external input
  2. Every output label is either a) consumed by a later atom, or b) marked as final output
  3. No duplicate output labels
  4. Input types match atom signatures
  5. No cycles in dependency graph (DAG)
"""

from .registry import get_atom
from .decomposer import AtomSequence
from .dep_graph import DepGraph, build_dep_graph


class ValidationError(Exception):
    pass


def validate(seq: AtomSequence) -> list[str]:
    """
    Validate an atom sequence.
    Returns a list of warnings (empty = all good).
    Raises ValidationError on hard errors.
    """
    warnings: list[str] = []
    produced: set[str] = set() | seq.input_labels

    # Rule 3: duplicate outputs
    seen_outputs: set[str] = set()
    for i, call in enumerate(seq.calls):
        if call.output in seen_outputs:
            raise ValidationError(
                f"Duplicate output label '{call.output}' at atom #{i}"
            )
        seen_outputs.add(call.output)

    # Rule 1 & 4: check each atom call
    for i, call in enumerate(seq.calls):
        sig = get_atom(call.opcode)

        # Check input count
        if len(call.inputs) != len(sig.input_types):
            raise ValidationError(
                f"Atom #{i} ({call.opcode}): expected {len(sig.input_types)} inputs, "
                f"got {len(call.inputs)}"
            )

        # Check each ref input is available
        for j, in_label in enumerate(call.ref_inputs()):
            if in_label not in produced:
                raise ValidationError(
                    f"Atom #{i} ({call.opcode}) ref input #{j} '${in_label}': "
                    f"not produced by any previous atom and not marked as external input"
                )

        produced.add(call.output)

    # Rule 2: check all produced labels are consumed
    consumed: set[str] = set()
    for call in seq.calls:
        consumed.update(call.ref_inputs())

    unused = produced - consumed - seq.output_labels - seq.input_labels
    if unused:
        warnings.append(f"Unused labels: {sorted(unused)}")

    # Rule 5: cycle check via dep graph
    dep_graph = build_dep_graph(seq)
    topo = dep_graph.topological_order()
    if len(topo) != len(seq.calls):
        raise ValidationError(
            f"Dependency cycle detected: {len(topo)} reachable, "
            f"{len(seq.calls)} total atoms"
        )

    return warnings

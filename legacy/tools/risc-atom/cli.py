"""
CLI for the RISC atom decomposer tool.

Usage:
  python -m tools.risc-atom decompose --task cdfg --ops '[{"id":"a"},{"id":"b","predecessors":["a"]}]'
  python -m tools.risc-atom validate --file task.json
  python -m tools.risc-atom list
  python -m tools.risc-atom demo
"""

import json
import sys
import argparse

from .registry import list_atoms, get_atom
from .decomposer import TaskDecomposer, AtomSequence
from .dep_graph import build_dep_graph
from .validator import validate, ValidationError
from .executor import Executor


def cmd_list():
    """List all registered atoms."""
    print("RISC Atom Registry")
    print("=" * 60)
    for opcode in list_atoms():
        sig = get_atom(opcode)
        inputs = ", ".join(sig.input_types) if sig.input_types else "()"
        print(f"  {opcode:<22} ({inputs}) → {sig.output_type:<12} cost={sig.cost}")
        print(f"    {sig.description}")


def cmd_decompose(args):
    """Decompose a task into atom sequence."""
    d = TaskDecomposer()

    if args.task == "cdfg":
        if not args.ops:
            print("Error: --ops required for cdfg task", file=sys.stderr)
            sys.exit(1)
        ops = json.loads(args.ops)
        seq = d.decompose_build_cdfg(ops)

    elif args.task == "schedule":
        if not args.cdfg:
            print("Error: --cdfg required for schedule task", file=sys.stderr)
            sys.exit(1)
        seq = d.decompose_schedule(args.cdfg)

    elif args.task == "list_sched":
        if not args.cdfg:
            print("Error: --cdfg required for list_sched task", file=sys.stderr)
            sys.exit(1)
        nr = int(args.resources) if args.resources else 2
        seq = d.decompose_list_schedule(args.cdfg, nr)

    elif args.task == "pipeline":
        if not args.ops:
            print("Error: --ops required for pipeline task", file=sys.stderr)
            sys.exit(1)
        ops = json.loads(args.ops)
        nr = int(args.resources) if args.resources else 2
        seq = d.decompose_full_pipeline(ops, nr)

    else:
        print(f"Unknown task: {args.task}", file=sys.stderr)
        print("Available: cdfg, schedule, list_sched, pipeline", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(seq.to_dict(), indent=2))
    else:
        print(f"Atom sequence: {len(seq)} atoms")
        print(seq.dump())


def cmd_validate(args):
    """Validate an atom sequence."""
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
        seq = AtomSequence.from_dict(data)
    elif args.stdin:
        data = json.load(sys.stdin)
        seq = AtomSequence.from_dict(data)
    else:
        print("Error: --file or --stdin required", file=sys.stderr)
        sys.exit(1)

    try:
        warnings = validate(seq)
        print(f"Validation: PASS ({len(seq)} atoms, {len(warnings)} warnings)")
        for w in warnings:
            print(f"  Warning: {w}")

        if args.graph:
            dep = build_dep_graph(seq)
            print("\nDependency graph:")
            print(dep.dump())

    except ValidationError as e:
        print(f"Validation: FAIL — {e}", file=sys.stderr)
        sys.exit(1)


def cmd_demo():
    """Run a demo: build CDFG, schedule, validate."""
    ops = [
        {"id": "a", "opcode": "load"},
        {"id": "b", "opcode": "load"},
        {"id": "c", "opcode": "add",  "predecessors": ["a", "b"]},
        {"id": "d", "opcode": "mul",  "predecessors": ["a"]},
        {"id": "e", "opcode": "add",  "predecessors": ["c", "d"]},
        {"id": "f", "opcode": "store","predecessors": ["e"]},
    ]

    print("Input operations:")
    for op in ops:
        preds = op.get("predecessors", [])
        print(f"  {op['id']}: {op['opcode']}" + (f"  ← [{', '.join(preds)}]" if preds else ""))

    print(f"\nDecomposing full pipeline ({len(ops)} ops)...")
    d = TaskDecomposer()
    seq = d.decompose_full_pipeline(ops, num_resources=2)

    print(f"\nGenerated {len(seq)} atom calls:")
    print(seq.dump())

    print("\nValidating...")
    try:
        warnings = validate(seq)
        print(f"  ✓ PASS — {len(warnings)} warnings")
        for w in warnings:
            print(f"  ⚠ {w}")
    except ValidationError as e:
        print(f"  ✗ FAIL — {e}")
        return

    print("\nDependency graph:")
    dep = build_dep_graph(seq)
    print(dep.dump())

    ready_count = len(dep.ready_set())
    print(f"\nInitially ready atoms: {ready_count}")
    topo = dep.topological_order()
    print(f"Topological execution order ({len(topo)} atoms):")
    print(f"  → {' → '.join(topo[:5])}...")

    print("\nExecuting...")
    exe = Executor()
    results = exe.run(seq)
    print(f"  Produced {len(results)} outputs")


def main():
    parser = argparse.ArgumentParser(description="RISC Atom Decomposer")
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List all registered atoms")

    # decompose
    dec = sub.add_parser("decompose", help="Decompose a task into atom sequence")
    dec.add_argument("--task", required=True, choices=["cdfg", "schedule", "list_sched", "pipeline"])
    dec.add_argument("--ops", help="JSON array of operations")
    dec.add_argument("--cdfg", help="Label of existing CDFG")
    dec.add_argument("--resources", help="Number of resources")
    dec.add_argument("--json-output", action="store_true", help="Output as JSON")

    # validate
    val = sub.add_parser("validate", help="Validate an atom sequence")
    val.add_argument("--file", help="JSON file with atom sequence")
    val.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    val.add_argument("--graph", action="store_true", help="Also print dependency graph")

    # demo
    sub.add_parser("demo", help="Run demo: CDFG → schedule → validate")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "decompose":
        cmd_decompose(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "demo":
        cmd_demo()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

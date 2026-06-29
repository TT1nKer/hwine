"""
Demo 3: 8-bit adder with carry_group rule, focused and fast.
Shows: ripple-carry → group composition → prefix tree emergence.
"""

from .gate_ir import Op
from .egraph import EGraph, ENode
from .rewrite import apply_all, ensure_constants, RULES, rule
from .extract import extract_optimal


# Register the carry group rule
@rule("carry_group")
def carry_group(eg: EGraph):
    """
    Pattern: c = OR(g, AND(p, c_in))
    If c_in has the same shape, create the group-composed equivalent.
    """
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)

    for cid, node in matches:
        or_left, or_right = node.children  # g, AND(p, c_in)
        g1_cid = or_left
        or_right_cls = eg.find(or_right)
        if or_right_cls not in eg.classes:
            continue
        for right_inner in list(eg.classes[or_right_cls].nodes):
            if right_inner.op != Op.AND or len(right_inner.children) != 2:
                continue
            p1_cid, c_in_cid = right_inner.children  # p1, c_in

            c_in_cls = eg.find(c_in_cid)
            if c_in_cls not in eg.classes:
                continue
            for c_inner in list(eg.classes[c_in_cls].nodes):
                if c_inner.op != Op.OR or len(c_inner.children) != 2:
                    continue
                c_or_left, c_or_right = c_inner.children
                c_or_right_cls = eg.find(c_or_right)
                if c_or_right_cls not in eg.classes:
                    continue
                for c_right_inner in list(eg.classes[c_or_right_cls].nodes):
                    if c_right_inner.op != Op.AND or len(c_right_inner.children) != 2:
                        continue
                    g0_cid = c_or_left
                    p0_cid = c_right_inner.children[0]
                    cin_cid = c_right_inner.children[1]

                    # Group G = OR(g1, AND(p1, g0))
                    and_int = eg.add(ENode(Op.AND, (p1_cid, g0_cid)))
                    G = eg.add(ENode(Op.OR, (g1_cid, eg.find(and_int))))

                    # Group P = AND(p1, p0)
                    P = eg.add(ENode(Op.AND, (p1_cid, p0_cid)))

                    # New carry: OR(G, AND(P, cin))
                    and_out = eg.add(ENode(Op.AND, (eg.find(P), cin_cid)))
                    new_c = eg.add(ENode(Op.OR, (eg.find(G), eg.find(and_out))))

                    target = eg.find(new_c)
                    if target >= 0 and target != cid:
                        eg.union(cid, target)
                        return  # One match per iteration to avoid explosion


def demo_8bit():
    print("=" * 60)
    print("8-bit Adder: Ripple → Group Associativity → Prefix Tree")
    print("=" * 60)

    eg = EGraph()
    ensure_constants(eg)

    inputs = {}
    for name in [f'a{i}' for i in range(8)] + [f'b{i}' for i in range(8)] + ['cin']:
        inputs[name] = eg.make_class()

    carry = inputs['cin']
    outputs = {}

    for i in range(8):
        a = inputs[f'a{i}']
        b = inputs[f'b{i}']
        g = eg.add(ENode(Op.AND, (a, b)))
        p = eg.add(ENode(Op.XOR, (a, b)))
        s = eg.add(ENode(Op.XOR, (p, carry)))
        outputs[f's{i}'] = eg.find(s)
        pc = eg.add(ENode(Op.AND, (p, carry)))
        carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))

    outputs['cout'] = eg.find(carry)

    print(f"Initial: {len(eg.classes)} classes, ripple depth ~8×(AND+OR) = 24")

    # Apply rules iteratively
    for it in range(8):
        before = len(eg.classes)
        for name, fn in RULES:
            fn(eg)
            eg.rebuild()
        after = len(eg.classes)
        delta = "+" + str(after - before) if after > before else ""
        print(f"  it{it+1}: {before} → {after} classes {delta}")
        if after == before:
            break

    # How many equivalent implementations of cout?
    cout_cid = outputs['cout']
    ecls = eg.classes.get(cout_cid)
    if ecls:
        print(f"\ncout has {len(ecls.nodes)} equivalent implementations:")
        for node in list(ecls.nodes):
            depth = compute_node_depth(eg, node, set())
            print(f"  depth={depth:4.1f}  {node}")

    # Extract best
    circuit = extract_optimal(eg, outputs, "adder8_opt")
    print(f"\nExtracted:")
    print(f"  gates: {circuit.node_count()}, depth: {circuit.depth()}, area: {circuit.total_area()}")
    print(f"  ripple depth: ~24.0, prefix depth: ~9.0 (3 levels)")


def compute_node_depth(eg: EGraph, node: ENode, visited: set) -> float:
    """Compute the depth of a node in the e-graph."""
    key = (node.op, node.children)
    if key in visited:
        return 0
    visited.add(key)
    max_child = 0
    for c in node.children:
        cid = eg.find(c)
        if cid in eg.classes:
            ecls = eg.classes[cid]
            if ecls.nodes:
                child_depths = []
                for cn in ecls.nodes:
                    child_depths.append(compute_node_depth(eg, cn, visited.copy()))
                max_child = max(max_child, max(child_depths) if child_depths else 0)
    depth = max_child + ({Op.AND: 1.5, Op.OR: 1.5, Op.XOR: 2.5, Op.NOT: 1.0}.get(node.op, 1))
    visited.discard(key)
    return depth


if __name__ == "__main__":
    demo_8bit()

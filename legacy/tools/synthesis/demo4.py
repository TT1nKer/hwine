"""
Demo 4: Aggressive carry-group rewrite.
Directly applies: c = OR(g1, AND(p1, OR(g0, AND(p0, cin))))
                    → c = OR(OR(g1, AND(p1, g0)), AND(AND(p1, p0), cin))

This is the algebraic step that enables tree reduction.
Apply it repeatedly to collapse the 8-level chain into a 3-level tree.
"""

from .gate_ir import Op
from .egraph import EGraph, ENode
from .rewrite import apply_all, ensure_constants, RULES, rule
from .extract import extract_optimal


@rule("carry_group")
def carry_group(eg: EGraph):
    """
    Group two adjacent carry levels into one group (G,P).
    Matches: c = OR(g1, AND(p1, OR(g0, AND(p0, cin))))
    Creates: c = OR(OR(g1, AND(p1, g0)), AND(AND(p1, p0), cin))
    This makes the associativity explicit.
    """
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    applied = 0

    for cid, node in matches:
        g1_cid = node.children[0]
        and_cid = node.children[1]
        and_cls = eg.find(and_cid)
        if and_cls not in eg.classes:
            continue

        for and_node in list(eg.classes[and_cls].nodes):
            if and_node.op != Op.AND or len(and_node.children) != 2:
                continue
            p1_cid, c_in_cid = and_node.children

            # Check if c_in is OR(g0, AND(p0, cin))
            c_in_cls = eg.find(c_in_cid)
            if c_in_cls not in eg.classes:
                continue

            for c_node in list(eg.classes[c_in_cls].nodes):
                if c_node.op != Op.OR or len(c_node.children) != 2:
                    continue
                g0_cid, and0_cid = c_node.children
                and0_cls = eg.find(and0_cid)
                if and0_cls not in eg.classes:
                    continue

                for and0_node in list(eg.classes[and0_cls].nodes):
                    if and0_node.op != Op.AND or len(and0_node.children) != 2:
                        continue
                    p0_cid, cin_cid = and0_node.children

                    # Group: G = OR(g1, AND(p1, g0))
                    t1 = eg.add(ENode(Op.AND, (p1_cid, g0_cid)))
                    G = eg.add(ENode(Op.OR, (g1_cid, eg.find(t1))))

                    # Group: P = AND(p1, p0)
                    P = eg.add(ENode(Op.AND, (p1_cid, p0_cid)))

                    # New: c = OR(G, AND(P, cin))
                    t2 = eg.add(ENode(Op.AND, (eg.find(P), cin_cid)))
                    new_c = eg.add(ENode(Op.OR, (eg.find(G), eg.find(t2))))

                    new_c = eg.find(new_c)
                    if new_c >= 0 and new_c != eg.find(cid):
                        eg.union(eg.find(cid), new_c)
                        applied += 1

                if applied >= 10:
                    break
            if applied >= 10:
                break
        if applied >= 10:
            break

    return applied


@rule("merge_groups")
def merge_groups(eg: EGraph):
    """
    Merge two adjacent group-level carries into a larger group.
    Same logic as carry_group, but operates at any level of the tree.
    """
    carry_group(eg)


def demo_8bit_aggressive():
    print("=" * 60)
    print("8-bit Adder: Aggressive Carry Grouping → Prefix Tree")
    print("=" * 60)

    eg = EGraph()
    ensure_constants(eg)

    inputs = {}
    for name in [f'a{i}' for i in range(8)] + [f'b{i}' for i in range(8)] + ['cin']:
        inputs[name] = eg.make_class()

    carry = inputs['cin']
    carry_signals = {}  # track each c_i
    outputs = {}
    carry_signals[0] = carry

    for i in range(8):
        a = inputs[f'a{i}']
        b = inputs[f'b{i}']
        g = eg.add(ENode(Op.AND, (a, b)))
        p = eg.add(ENode(Op.XOR, (a, b)))
        s = eg.add(ENode(Op.XOR, (p, carry)))
        outputs[f's{i}'] = eg.find(s)
        pc = eg.add(ENode(Op.AND, (p, carry)))
        carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))
        carry_signals[i+1] = carry

    outputs['cout'] = eg.find(carry)

    print(f"Initial: {len(eg.classes)} classes")
    print(f"  cout = c8 ({len(list(eg.classes[outputs['cout']].nodes))} impls)")

    # Apply rules, show progress
    for it in range(10):
        before = len(eg.classes)
        for name, fn in RULES:
            fn(eg)
        eg.rebuild()
        after = len(eg.classes)
        cout_cid = eg.find(outputs['cout'])
        n_impls = len(eg.classes[cout_cid].nodes) if cout_cid in eg.classes else 0
        print(f"  it{it+1}: {before}→{after} classes, cout has {n_impls} impls")
        if after == before:
            break

    # Show all cout implementations with their depths
    cout_cid = eg.find(outputs['cout'])
    if cout_cid in eg.classes:
        ecls = eg.classes[cout_cid]
        print(f"\ncout implementations (depth):")
        for node in list(ecls.nodes)[:8]:
            d = simple_depth(node)
            print(f"  depth={d:4.1f}  {node}")

    # Extract best circuit
    circuit = extract_optimal(eg, outputs, "adder8_tree")
    print(f"\nExtracted circuit:")
    print(f"  gates: {circuit.node_count()}, depth: {circuit.depth()}, area: {circuit.total_area()}")
    print(f"  Theoretical: ripple=24.0, prefix=9.0")


def simple_depth(node: ENode, visited=None) -> float:
    if visited is None:
        visited = set()
    nid = id(node)
    if nid in visited:
        return 0
    visited.add(nid)
    op_d = {Op.AND: 1.5, Op.OR: 1.5, Op.XOR: 2.5, Op.NOT: 1.0}.get(node.op, 1)
    max_c = 0
    for c in node.children:
        if isinstance(c, ENode):
            max_c = max(max_c, simple_depth(c, visited.copy()))
    return max_c + op_d


if __name__ == "__main__":
    demo_8bit_aggressive()

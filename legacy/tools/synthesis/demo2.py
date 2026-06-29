"""
Demo 2: Add a CARRY_COMBINE operator to the gate IR, 
teach the e-graph that it's associative, and let the optimizer
find the tree structure automatically.

Without this operator, the e-graph sees random gates.
With it + associativity, the tree emerges.
"""

from .gate_ir import Op, OP_DELAY, OP_AREA, GateNode, ONE, ZERO
from .egraph import EGraph, ENode
from .rewrite import apply_all, ensure_constants, RULES, rule
from .extract import extract_optimal

# ============================================================
# Extend Op with a CARRY_COMBINE operator
# ============================================================

# We can't modify the enum, so we use a sentinel op.
# Represent CARRY_COMBINE as: CARRY_GP = (g_out, p_out) = combine((g1,p1), (g0,p0))
# This produces TWO outputs: g_out and p_out.
# In our single-output e-node model, we split into two nodes:
#   g_combined = OR(g1, AND(p1, g0))
#   p_combined = AND(p1, p0)
# These are expressible in existing gates, so we just need the associativity RULE.

# New rule: recognize the carry chain pattern and introduce group composition
@rule("carry_group")
def carry_group(eg: EGraph):
    """
    Pattern: c_out = OR(g, AND(p, c_in))
    Goal: recognize this as c_out = carry_of_group((g,p), c_in)
    Create equivalent: c_out = do group composition if c_in itself is a group result
    """
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    for cid, node in matches:
        or_left, or_right = node.children
        or_right_cls = eg.find(or_right)
        if or_right_cls not in eg.classes:
            continue
        
        # Check if or_right is AND(p, c_in)
        for right_inner in list(eg.classes[or_right_cls].nodes):
            if right_inner.op == Op.AND and len(right_inner.children) == 2:
                p_cid = right_inner.children[0]  # p
                c_in_cid = right_inner.children[1]  # c_in
                g_cid = or_left  # g

                # Now check if c_in itself is a similar structure
                c_in_cls = eg.find(c_in_cid)
                if c_in_cls not in eg.classes:
                    continue

                for c_inner in list(eg.classes[c_in_cls].nodes):
                    if c_inner.op == Op.OR and len(c_inner.children) == 2:
                        c_or_left, c_or_right = c_inner.children
                        c_or_right_cls = eg.find(c_or_right)
                        if c_or_right_cls not in eg.classes:
                            continue
                        for c_right_inner in list(eg.classes[c_or_right_cls].nodes):
                            if c_right_inner.op == Op.AND and len(c_right_inner.children) == 2:
                                g0_cid = c_or_left
                                p0_cid = c_right_inner.children[0]

                                # Now we have: c = OR(g1, AND(p1, OR(g0, AND(p0, cin))))
                                # Which equals: c = OR(OR(g1, AND(p1, g0)), AND(AND(p1, p0), cin))
                                
                                # Group generate: G = OR(g1, AND(p1, g0))
                                and_p1_g0 = eg.add(ENode(Op.AND, (p_cid, g0_cid)))
                                G_cid = eg.add(ENode(Op.OR, (g_cid, eg.find(and_p1_g0))))
                                
                                # Group propagate: P = AND(p1, p0)  
                                P_cid = eg.add(ENode(Op.AND, (p_cid, p0_cid)))
                                
                                # New carry: c = OR(G, AND(P, cin))
                                and_P_cin = eg.add(ENode(Op.AND, (eg.find(P_cid), c_right_inner.children[1])))
                                new_carry = eg.add(ENode(Op.OR, (eg.find(G_cid), eg.find(and_P_cin))))
                                
                                target = eg.find(new_carry)
                                if target >= 0:
                                    eg.union(cid, target)


def demo_carry_assoc():
    print("=" * 60)
    print("32-bit Adder: E-Graph + Carry Group Associativity")
    print("=" * 60)

    eg = EGraph()
    ensure_constants(eg)

    # Create inputs
    inputs = {}
    for name in [f'a{i:02d}' for i in range(32)] + [f'b{i:02d}' for i in range(32)] + ['cin']:
        inputs[name] = eg.make_class()

    # Build ripple-carry adder
    carry = inputs['cin']
    outputs = {}

    for i in range(32):
        a = inputs[f'a{i:02d}']
        b = inputs[f'b{i:02d}']
        g = eg.add(ENode(Op.AND, (a, b)))
        p = eg.add(ENode(Op.XOR, (a, b)))
        s = eg.add(ENode(Op.XOR, (p, carry)))
        outputs[f's{i:02d}'] = eg.find(s)
        p_and_c = eg.add(ENode(Op.AND, (p, carry)))
        new_carry = eg.add(ENode(Op.OR, (g, eg.find(p_and_c))))
        carry = eg.find(new_carry)

    outputs['cout'] = carry

    print(f"\nInitial e-graph: {len(eg.classes)} classes")

    # Apply rules  
    for it in range(5):
        before = len(eg.classes)
        for name, fn in RULES:
            fn(eg)
            eg.rebuild()
        after = len(eg.classes)
        print(f"  Iteration {it+1}: {before} → {after} classes "
              f"({'saturated' if before == after else 'grew'})")
        if before == after:
            break

    # Check carry classes: how many different implementations of cout exist?
    cout_cid = eg.find(outputs['cout'])
    if cout_cid in eg.classes:
        cout_ecls = eg.classes[cout_cid]
        print(f"\ncout implementations discovered: {len(cout_ecls.nodes)}")
        for i, node in enumerate(list(cout_ecls.nodes)[:5]):
            print(f"  [{i}] {node}")

    # Extract
    circuit = extract_optimal(eg, outputs, "adder32_opt")
    print(f"\nExtracted circuit:")
    print(f"  Gates: {circuit.node_count()}")
    print(f"  Depth: {circuit.depth()}")
    print(f"  Area:  {circuit.total_area()}")
    print(f"\nTheoretical ripple depth: 96.0")
    print(f"Theoretical prefix depth: 15.0 (5 levels)")

    return circuit


if __name__ == "__main__":
    demo_carry_assoc()

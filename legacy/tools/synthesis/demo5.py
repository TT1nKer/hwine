"""
Demo 5: Gate-level optimization of an int4×int4 multiplier.
Shows: partial products → adder tree → e-graph saturation → optimal extraction.

The multiplier decomposes into:
  1. 16 partial product bits (AND gates)
  2. A carry-save adder tree to reduce 4 rows to 1 result
  3. The e-graph can discover tree-level associativity optimizations

This is the first step toward gate-level optimization of the DotInt4Tile MAC unit.
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

                    t1 = eg.add(ENode(Op.AND, (p1_cid, g0_cid)))
                    G = eg.add(ENode(Op.OR, (g1_cid, eg.find(t1))))
                    P = eg.add(ENode(Op.AND, (p1_cid, p0_cid)))
                    t2 = eg.add(ENode(Op.AND, (eg.find(P), cin_cid)))
                    new_c = eg.add(ENode(Op.OR, (eg.find(G), eg.find(t2))))

                    new_c = eg.find(new_c)
                    if new_c >= 0 and new_c != eg.find(cid):
                        eg.union(eg.find(cid), new_c)
                        applied += 1

                if applied >= 5:
                    break
            if applied >= 5:
                break
        if applied >= 5:
            break

    return applied


def build_mul4(eg: EGraph, a_3_0: list, b_3_0: list) -> dict:
    """
    Build a 4-bit × 4-bit unsigned multiplier at gate level.
    Inputs: a[0..3], b[0..3] (LSB first)
    Outputs: p[0..7]
    
    Structure:
      p0 = a0 & b0
      row1: a0*b1, a1*b0  → half adder → p1 + c1
      row2: a0*b2, a1*b1, a2*b0 + c1 → full adder chain
      row3: a0*b3, a1*b2, a2*b1, a3*b0 + carries
      row4: a1*b3, a2*b2, a3*b1 + carries
      row5: a2*b3, a3*b2 + carries
      row6: a3*b3 + carries → p6, p7
    """
    # 16 partial products
    pp = {}
    for i in range(4):
        for j in range(4):
            pp[(i, j)] = eg.find(eg.add(ENode(Op.AND, (a_3_0[i], b_3_0[j]))))

    outputs = {}
    carries_at_bit = {}  # bit position → list of carry signals to add

    # Bit 0: just a0*b0
    outputs['p0'] = pp[(0, 0)]

    # Bit 1: a0*b1 + a1*b0 (half adder)
    s1 = eg.find(eg.add(ENode(Op.XOR, (pp[(0, 1)], pp[(1, 0)]))))
    c1 = eg.find(eg.add(ENode(Op.AND, (pp[(0, 1)], pp[(1, 0)]))))
    outputs['p1'] = s1
    carries_at_bit.setdefault(2, []).append(c1)

    # Bit 2: a0*b2 + a1*b1 + a2*b0 + carry from bit1
    # Build ripple chain for this column
    terms2 = [pp[(0, 2)], pp[(1, 1)], pp[(2, 0)]] + carries_at_bit.get(2, [])
    s2, c2 = ripple_add_column(eg, terms2)
    outputs['p2'] = s2
    if c2 is not None:
        carries_at_bit.setdefault(3, []).append(c2)

    # Bit 3: a0*b3 + a1*b2 + a2*b1 + a3*b0 + carries
    terms3 = [pp[(0, 3)], pp[(1, 2)], pp[(2, 1)], pp[(3, 0)]] + carries_at_bit.get(3, [])
    s3, c3_to_4 = ripple_add_column(eg, terms3)
    outputs['p3'] = s3
    if c3_to_4 is not None:
        carries_at_bit.setdefault(4, []).append(c3_to_4)

    # Bit 4: a1*b3 + a2*b2 + a3*b1 + carries
    terms4 = [pp[(1, 3)], pp[(2, 2)], pp[(3, 1)]] + carries_at_bit.get(4, [])
    s4, c4_to_5 = ripple_add_column(eg, terms4)
    outputs['p4'] = s4
    if c4_to_5 is not None:
        carries_at_bit.setdefault(5, []).append(c4_to_5)

    # Bit 5: a2*b3 + a3*b2 + carries
    terms5 = [pp[(2, 3)], pp[(3, 2)]] + carries_at_bit.get(5, [])
    s5, c5_to_6 = ripple_add_column(eg, terms5)
    outputs['p5'] = s5
    if c5_to_6 is not None:
        carries_at_bit.setdefault(6, []).append(c5_to_6)

    # Bit 6: a3*b3 + carries
    terms6 = [pp[(3, 3)]] + carries_at_bit.get(6, [])
    s6, c6_to_7 = ripple_add_column(eg, terms6)
    outputs['p6'] = s6
    if c6_to_7 is not None:
        outputs['p7'] = c6_to_7
    else:
        outputs['p7'] = None

    # Filter None outputs
    return {k: v for k, v in outputs.items() if v is not None}


def ripple_add_column(eg: EGraph, terms: list) -> tuple:
    """
    Add a list of terms at the same bit position using ripple-carry chain.
    terms: list of canonical e-class IDs to add together.
    Returns: (sum, carry_out) canonical IDs.
    Each term is a 1-bit signal, result is 1-bit sum + carry.
    For multiple terms, chain them: (t0 XOR t1 XOR t2 ...), carry propagates.
    """
    if len(terms) == 0:
        return None, None
    if len(terms) == 1:
        return terms[0], None

    # Chain: accumulate through ripple
    acc_sum = terms[0]
    acc_carry = None

    for i in range(1, len(terms)):
        ti = terms[i]

        # First full adder: acc_sum + ti
        s = eg.find(eg.add(ENode(Op.XOR, (acc_sum, ti))))
        c = eg.find(eg.add(ENode(Op.AND, (acc_sum, ti))))

        if acc_carry is not None:
            # Second full adder: s + acc_carry
            s2 = eg.find(eg.add(ENode(Op.XOR, (s, acc_carry))))
            c2 = eg.find(eg.add(ENode(Op.AND, (s, acc_carry))))
            # The two carries need to be ORed
            cout = eg.find(eg.add(ENode(Op.OR, (c, c2))))
            acc_carry = cout
            acc_sum = s2
        else:
            acc_carry = c
            acc_sum = s

    return acc_sum, acc_carry


def demo_mul4():
    print("=" * 60)
    print("4×4 Multiplier: Gate-Level → E-Graph → Optimal Extraction")
    print("=" * 60)

    eg = EGraph()
    ensure_constants(eg)

    # Create primary inputs: a[3:0], b[3:0] (4 bits each, LSB-first)
    a = [eg.make_class() for _ in range(4)]
    b = [eg.make_class() for _ in range(4)]

    # Build multiplier
    outputs = build_mul4(eg, a, b)

    initial_classes = len(eg.classes)
    print(f"\nInitial e-graph: {initial_classes} classes")
    print(f"Output bits: {len(outputs)}")

    # Show the carry chain structure
    print(f"\nApplying rewrite rules...")
    for it in range(8):
        before = len(eg.classes)
        for name, fn in RULES:
            fn(eg)
        eg.rebuild()
        after = len(eg.classes)
        print(f"  it{it+1}: {before} → {after} classes "
              f"({'saturated' if before == after else 'grew'})")
        if after == before:
            break

    # Check if any output has multiple implementations
    print(f"\nEquivalence discoveries per output:")
    for name, cid in sorted(outputs.items()):
        cid = eg.find(cid)
        if cid in eg.classes:
            n = len(eg.classes[cid].nodes)
            print(f"  {name}: {n} equivalent implementations")
            if n > 1:
                for node in list(eg.classes[cid].nodes)[:3]:
                    print(f"    {node}")

    # Extract optimal
    circuit = extract_optimal(eg, outputs, "mul4_optimal")
    print(f"\nExtracted circuit:")
    print(f"  gates: {circuit.node_count()}")
    print(f"  depth: {circuit.depth()}")
    print(f"  area:  {circuit.total_area()}")

    # Build a simple reference for comparison
    ref_eg = EGraph()
    ref_a = [ref_eg.make_class() for _ in range(4)]
    ref_b = [ref_eg.make_class() for _ in range(4)]
    ref_out = build_mul4(ref_eg, ref_a, ref_b)
    ref_circuit = extract_optimal(ref_eg, ref_out, "mul4_ref")
    print(f"\nReference (no optimization):")
    print(f"  gates: {ref_circuit.node_count()}")
    print(f"  depth: {ref_circuit.depth()}")
    print(f"  area:  {ref_circuit.total_area()}")

    improvement = ref_circuit.total_area() - circuit.total_area()
    print(f"\nImprovement: {improvement:.0f} area ({100*improvement/ref_circuit.total_area():.1f}%)")

    return circuit


if __name__ == "__main__":
    demo_mul4()

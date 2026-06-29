"""
Demo: 4-bit ripple-carry adder → e-graph saturation → discover parallel prefix.

The key insight we want to see emerge:
  - The carry chain c_{i+1} = g_i | (p_i & c_i) is associative
  - After saturation, multiple carry computation trees exist in the e-graph
  - The extractor can pick the shallowest (log-depth) tree
"""

from .gate_ir import Op
from .egraph import EGraph, ENode
from .rewrite import apply_all, ensure_constants, ZERO_CLASS, ONE_CLASS
from .extract import extract_optimal


def demo_adder_4bit():
    print("=" * 60)
    print("4-bit Adder: Ripple-Carry → E-Graph → Optimal Extraction")
    print("=" * 60)

    eg = EGraph()
    ensure_constants(eg)

    # --- Step 1: Create input e-classes (primary inputs) ---
    inputs = {}
    for name in ['a0','a1','a2','a3','b0','b1','b2','b3','cin']:
        cid = eg.make_class()
        inputs[name] = cid

    # --- Step 2: Build ripple-carry adder at gate level ---
    # For each bit i:
    #   g_i = a_i & b_i          (generate)
    #   p_i = a_i ^ b_i          (propagate)
    #   s_i = p_i ^ c_i          (sum)
    #   c_{i+1} = g_i | (p_i & c_i)   (carry)

    carry = inputs['cin']
    outputs = {}

    for i in range(4):
        a = inputs[f'a{i}']
        b = inputs[f'b{i}']

        # g_i: generate
        g = eg.add(ENode(Op.AND, (a, b)))

        # p_i: propagate
        p = eg.add(ENode(Op.XOR, (a, b)))

        # s_i: sum = p_i ^ c_i
        s = eg.add(ENode(Op.XOR, (p, carry)))
        outputs[f's{i}'] = eg.find(s)

        # c_{i+1} = g_i | (p_i & c_i)
        p_and_c = eg.add(ENode(Op.AND, (p, carry)))
        new_carry = eg.add(ENode(Op.OR, (g, eg.find(p_and_c))))
        carry = eg.find(new_carry)

    outputs['cout'] = carry

    print(f"\nInitial e-graph: {len(eg.classes)} e-classes")
    print(f"Outputs: {outputs}")

    # --- Step 3: Apply rewrite rules (saturation) ---
    print(f"\nApplying rewrite rules...")
    iterations = apply_all(eg, max_iter=5)
    print(f"Saturated after {iterations} iterations")
    print(f"Final e-graph: {len(eg.classes)} e-classes")

    # --- Step 4: Extract optimal circuit ---
    print(f"\nExtracting optimal circuit...")
    circuit = extract_optimal(eg, outputs, "adder4_optimal")
    print(f"\n{circuit.dump()}")

    print(f"\n=== Key metrics ===")
    print(f"Gates: {circuit.node_count()}")
    print(f"Critical path depth: {circuit.depth()}")
    print(f"Area: {circuit.total_area()}")

    # Compare with theoretical:
    # Ripple-carry depth: 4 × (XOR + AND + OR) ≈ 4 × 5 = 20
    # Parallel prefix depth: log2(4) × (AND + OR) + XOR ≈ 2 × 3 + 2.5 = 8.5
    print(f"\nTheoretical reference:")
    print(f"  Ripple-carry depth: ~20 (4 × 5)")
    print(f"  Parallel prefix depth: ~8.5 (log2(4)×3 + 2.5)")

    return circuit


if __name__ == "__main__":
    demo_adder_4bit()

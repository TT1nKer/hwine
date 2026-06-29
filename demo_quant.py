#!/usr/bin/env python3
"""
Demo: Meta-operation e-graph for quantization hardware optimization.

Demonstrates:
  1. Decompose int4 GEMM MAC tile into meta-operations
  2. Insert into e-graph
  3. Apply rewrite rules (associativity, fusion, identity, acc→tree)
  4. Extract optimized structures
  5. Show: serial accumulation → tree reduction discovery
"""

import sys
import os
import time

# Allow running as script or module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.meta_ir import AtomOp, ENode, OP_COST, OP_LATENCY
from tools.meta_egraph import EGraph
from tools.meta_rewrite import ALL_RULES, FAST_RULES


def build_int4_mac_tile(eg: EGraph, n_macs: int = 8) -> int:
    """
    Build an int4 GEMM MAC tile:
      - n_macs multiply-accumulate operations (int4 weight × int8 activation)
      - Serial accumulation: ACC_STEP(ACC_STEP(...(ACC_INIT(0), MAC0), MAC1)...)
      - Each MAC: MUL(DEQUANT_W(int4_weight), int8_activation) + accumulator
    
    Returns the e-class ID of the final accumulator state.
    """
    # Create a zero constant
    zero = eg.add(ENode(AtomOp.ZERO, ()))

    # Create weight and activation variables
    vars_w = []
    vars_a = []
    for i in range(n_macs):
        w = eg.add(ENode(AtomOp.VAR, (f"w{i}",)))  # int4 weight
        a = eg.add(ENode(AtomOp.VAR, (f"a{i}",)))  # int8 activation
        vars_w.append(w)
        vars_a.append(a)

    # Build serial accumulator chain
    acc_init = eg.add(ENode(AtomOp.ACC_INIT, (zero,)))
    acc_state = acc_init

    for i in range(n_macs):
        # Multiply: weight × activation
        mul = eg.add(ENode(AtomOp.MUL, (vars_w[i], vars_a[i])))
        # Accumulate: acc_state += mul
        acc_state = eg.add(ENode(AtomOp.ACC_STEP, (acc_state, mul)))

    # Also build an alternative representation: explicit MAC chain
    # MAC(w, a, acc) — this is the fused view
    mac_chain = acc_init
    for i in range(n_macs):
        mac_chain = eg.add(ENode(AtomOp.MAC, (vars_w[i], vars_a[i], mac_chain)))

    # Make the MAC chain equivalent to the ACC chain
    # (this is the key equivalence we want the e-graph to exploit)
    eg._union(acc_state, mac_chain)

    return eg._canon(acc_state)


def build_add_chain(eg: EGraph, n: int = 8) -> int:
    """
    Build a serial ADD chain: ADD(ADD(...(a0, a1), a2)..., a{n-1}).
    This should be discoverable as a tree via associativity.
    Returns the e-class ID of the final sum.
    """
    vars_a = []
    for i in range(n):
        v = eg.add(ENode(AtomOp.VAR, (f"a{i}",)))
        vars_a.append(v)

    chain = vars_a[0]
    for i in range(1, n):
        chain = eg.add(ENode(AtomOp.ADD, (chain, vars_a[i])))

    return chain


def analyze_egraph(eg: EGraph, target_cid: int, label: str = ""):
    """Analyze and report what the e-graph discovered."""
    cid = eg._canon(target_cid)
    ecls = eg.classes[cid]

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  E-class size: {len(ecls.nodes)} equivalent representations")
    print(f"  Total e-classes: {len(eg.classes)}")
    print(f"  Total unions: {eg.union_count}")
    print()

    # Show all representations in this e-class
    print("  Equivalent representations in target e-class:")
    for node in sorted(ecls.nodes, key=lambda n: (OP_COST.get(n.op, 1), n.op.name)):
        cost = OP_COST.get(node.op, 1)
        depth = OP_LATENCY.get(node.op, 1)
        print(f"    [{cost}c/{depth}d] {node}")

    # Extract best by cost
    best_cost, cost_val = eg.extract_optimal(cid)
    print(f"\n  Best cost tree (cost={cost_val:.0f}):")
    print_tree(eg, cid, cost=True)

    # Extract best by depth
    best_depth, depth_val = eg.extract_depth(cid)
    print(f"\n  Best depth tree (depth={depth_val:.0f}):")
    print_tree(eg, cid, depth=True)


def print_tree(eg: EGraph, cid: int, cost: bool = False, depth: bool = False,
               indent: int = 0, visited: set = None):
    """Recursively print the best extraction tree."""
    if visited is None:
        visited = set()
    cid = eg._canon(cid)
    if cid in visited:
        print(f"{'  ' * indent}... (cycle to C{cid})")
        return
    visited.add(cid)

    if cid not in eg.classes:
        print(f"{'  ' * indent}C{cid}?")
        return

    if cost:
        node, _ = eg.extract_optimal(cid)
    elif depth:
        node, _ = eg.extract_depth(cid)
    else:
        node, _ = eg.extract_optimal(cid)

    if node is None:
        print(f"{'  ' * indent}∅")
        return

    label = f"{node.op.name}"
    if node.op == AtomOp.VAR and node.children:
        label += f"({node.children[0]})"
    if node.op == AtomOp.CONST and node.children:
        label += f"={node.children[0]}"

    if node.children:
        print(f"{'  ' * indent}{label}")
        for ch in node.children:
            print_tree(eg, ch, cost, depth, indent + 1, visited)
    else:
        print(f"{'  ' * indent}{label}")


def demo_int4_mac_tile():
    """Demo 1: int4 GEMM MAC tile — serial accumulation → tree reduction."""
    eg = EGraph()

    print("Building int4 MAC tile (8 MACs, serial accumulation)...")
    target = build_int4_mac_tile(eg, n_macs=8)
    print(f"  Initial: {len(eg.classes)} e-classes")

    print("Applying rewrite rules...")
    t0 = time.time()
    iters = eg.saturate(FAST_RULES, max_iter=20)
    dt = time.time() - t0
    analyze_egraph(eg, target, f"int4 MAC tile (8 MACs) — {iters} iterations, {dt:.3f}s")


def demo_add_chain():
    """Demo 2: Simple ADD chain — associativity discovers binary tree."""
    for n in [4, 8, 16, 32]:
        eg = EGraph()
        target = build_add_chain(eg, n)
        t0 = time.time()
        eg.saturate(FAST_RULES, max_iter=10)
        dt = time.time() - t0
        cid = eg._canon(target)
        n_repr = len(eg.classes[cid].nodes)
        print(f"  {n}-wide ADD chain: {len(eg.classes)} classes, {n_repr} reprs in target, {dt:.3f}s")

    # Detailed analysis of 8-element chain
    print()
    eg = EGraph()
    target = build_add_chain(eg, 8)
    eg.saturate(FAST_RULES, max_iter=20)
    analyze_egraph(eg, target, "8-wide ADD chain → tree discovery")


def demo_mac_vs_muladd():
    """Demo 3: MAC decomposition and fusion equilibrium."""
    eg = EGraph()

    w = eg.add(ENode(AtomOp.VAR, ("w",)))
    a = eg.add(ENode(AtomOp.VAR, ("a",)))
    acc = eg.add(ENode(AtomOp.ZERO, ()))

    # MAC representation
    mac = eg.add(ENode(AtomOp.MAC, (w, a, acc)))

    # Also build: ADD(MUL(w,a), acc) — should be equivalent to MAC
    mul = eg.add(ENode(AtomOp.MUL, (w, a)))
    add_explicit = eg.add(ENode(AtomOp.ADD, (mul, acc)))

    print("Building MAC vs MUL+ADD representations...")
    print(f"  MAC class: C{eg._canon(mac)}")
    print(f"  ADD(MUL(w,a),0) class: C{eg._canon(add_explicit)}")
    print(f"  Same class before rules: {eg._canon(mac) == eg._canon(add_explicit)}")

    eg.saturate(FAST_RULES, max_iter=10)
    print(f"  Same class after rules: {eg._canon(mac) == eg._canon(add_explicit)}")

    cid = eg._canon(mac)
    ecls = eg.classes[cid]
    print(f"  Final e-class has {len(ecls.nodes)} representations:")
    for node in ecls.nodes:
        print(f"    {node}")


def demo_quant_fold():
    """Demo 4: Quantization folding."""
    eg = EGraph()

    # int4 weight variable
    w4 = eg.add(ENode(AtomOp.VAR, ("w4",)))
    scale = eg.add(ENode(AtomOp.VAR, ("scale",)))
    zp = eg.add(ENode(AtomOp.VAR, ("zp",)))

    # Dequantized weight: w_fp = (w4 - zp) * scale
    deq_w = eg.add(ENode(AtomOp.DEQUANT_W, (w4, scale, zp)))

    # Activation
    act = eg.add(ENode(AtomOp.VAR, ("act",)))

    # Multiply: MUL(deq_w, act)
    mul = eg.add(ENode(AtomOp.MUL, (deq_w, act)))

    print("Building quant-aware multiply: MUL(DEQUANT_W(w4), act)")
    print(f"  Initial: {len(eg.classes)} classes")

    eg.saturate(FAST_RULES, max_iter=10)
    print(f"  After saturation: {len(eg.classes)} classes")

    cid = eg._canon(mul)
    print(f"  Representations of MUL node:")
    for node in eg.classes[cid].nodes:
        print(f"    {node}")


if __name__ == "__main__":
    print("=" * 60)
    print("  hwine — Meta-Operation E-Graph Demo")
    print("  Quantization hardware: discover structural equivalences")
    print("=" * 60)

    demo_add_chain()
    demo_int4_mac_tile()
    demo_mac_vs_muladd()
    demo_quant_fold()

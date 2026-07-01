#!/usr/bin/env python3
"""
hwine — End-to-End FPGA Demo
=============================
int4 MAC tile → meta-ops → e-graph saturation → FPGA-optimal extraction → Pareto front

Demonstrates: serial accumulation → tree discovery → FPGA cost evaluation
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.meta_ir import AtomOp, ENode, fpga_cost_fn, max_freq_mhz
from tools.meta_ir import FPGA_LUT_COST, FPGA_DSP_COST, FPGA_FF_COST, FPGA_DELAY_NS
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES, FPGA_RULES, ALL_RULES


def log(s=""):
    print(s, flush=True)


def hline(title=""):
    log(f"\n{'─'*60}")
    if title:
        log(f"  {title}")
        log(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════
# Builder: int4×int8 MAC tile
# ═══════════════════════════════════════════════════════════════

def build_int4_mac_tile(eg: EGraph, n_macs: int = 8,
                         use_mac_chain: bool = True) -> int:
    """Build an int4 GEMM MAC tile:
    - n_macs weights (int4) × activations (int8)
    - Serial accumulation: ACC_STEP(...(ACC_INIT, MAC0)...MAC7)
    - Also build MAC chain representation and unify
    
    Returns e-class ID of the final accumulator state.
    """
    zero = eg.add(ENode(AtomOp.ZERO, ()))
    vars_w = [eg.add(ENode(AtomOp.VAR, (f"w{i}",))) for i in range(n_macs)]
    vars_a = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(n_macs)]

    # Serial accumulator chain
    acc_init = eg.add(ENode(AtomOp.ACC_INIT, (zero,)))
    acc_state = acc_init
    for i in range(n_macs):
        mul = eg.add(ENode(AtomOp.MUL, (vars_w[i], vars_a[i])))
        acc_state = eg.add(ENode(AtomOp.ACC_STEP, (acc_state, mul)))

    if use_mac_chain:
        # MAC chain: MAC(w0,a0, MAC(w1,a1, ... ACC_INIT(0)))
        mac_chain = acc_init
        for i in range(n_macs):
            mac_chain = eg.add(ENode(AtomOp.MAC, (vars_w[i], vars_a[i], mac_chain)))
        eg._union(acc_state, mac_chain)

    return eg._canon(acc_state)


# ═══════════════════════════════════════════════════════════════
# Analysis: print FPGA stats for a given e-class
# ═══════════════════════════════════════════════════════════════

def analyze_target(eg: EGraph, target_cid: int, label: str = ""):
    """Full analysis of a target e-class after saturation."""
    cid = eg._canon(target_cid)
    ecls = eg.classes[cid]
    n_repr = len(ecls.nodes)

    # Extract FPGA-optimal
    best_node, stats = eg.extract_fpga_optimal(cid)

    # Extract Pareto front
    pareto = eg.extract_pareto_front(cid)

    hline(label)
    log(f"  E-graph: {len(eg.classes)} classes, {eg.union_count} unions, {n_repr} reprs in target")
    log()

    # ── FPGA optimal ──
    log(f"  ╔══ FPGA-Optimal Extraction ══╗")
    log(f"  ║ LUTs:      {stats['lut']:8.1f}           ║")
    log(f"  ║ DSPs:      {stats['dsp']:8.1f}           ║")
    log(f"  ║ FF:        {stats['ff']:8.1f}           ║")
    log(f"  ║ Crit path: {stats['delay_ns']:8.2f} ns       ║")
    log(f"  ║ Fmax:      {stats['fmax_mhz']:8.1f} MHz       ║")
    log(f"  ║ Cycles:    {stats['cycles']:8.0f}           ║")
    log(f"  ╚════════════════════════════════╝")
    log()

    # ── Pareto front ──
    if pareto:
        log(f"  Pareto Frontier ({len(pareto)} points):")
        log(f"  {'Area':>10} {'Delay ns':>10} {'Fmax MHz':>10} {'Repr'}")
        log(f"  {'─'*10} {'─'*10} {'─'*10} {'─'*20}")
        for p in pareto[:10]:
            area = p['lut'] + p['dsp'] * 10
            log(f"  {area:10.1f} {p['delay_ns']:10.2f} {p['fmax_mhz']:10.0f} {p['repr'][:40]}")

    log()

    # ── Print optimal tree ──
    log(f"  Best FPGA tree (LUT={stats['lut']:.1f}, DSP={stats['dsp']:.1f}, "
        f"delay={stats['delay_ns']:.2f}ns, fmax={stats['fmax_mhz']:.0f}MHz):")
    print_fpga_tree(eg, cid)


def print_fpga_tree(eg: EGraph, cid: int, indent: int = 0, visited: set = None):
    """Recursively print best-FPGA tree."""
    if visited is None:
        visited = set()
    cid = eg._canon(cid)
    if cid in visited:
        log(f"{'  '*indent}...⬆")
        return
    visited.add(cid)
    if cid not in eg.classes:
        return

    best_node, _ = eg.extract_fpga_optimal(cid)
    if best_node is None:
        return

    op = best_node.op.name
    delay = FPGA_DELAY_NS.get(best_node.op, 0)
    dsp = "🎯" if FPGA_DSP_COST.get(best_node.op, 0) > 0 else "  "
    pipe_tag = "⏱ " if best_node.op == AtomOp.PIPE else ""

    if best_node.op == AtomOp.VAR and best_node.children:
        for ch_node in eg.classes[eg._canon(best_node.children[0])].nodes:
            if ch_node.op == AtomOp.STR_LIT:
                op = f"VAR({ch_node.meta})"
                break

    log(f"{'  '*indent}{pipe_tag}{dsp}{op} [{delay:.1f}ns]")

    for ch in best_node.children:
        print_fpga_tree(eg, ch, indent + 1, visited)


# ═══════════════════════════════════════════════════════════════
# Main demos
# ═══════════════════════════════════════════════════════════════

def demo_int4_mac_tile():
    """Demo 1: int4 MAC tile — serial → tree discovery with FPGA costs."""
    log()
    log("╔" + "═" * 58 + "╗")
    log("║  Demo 1: int4×int8 MAC tile (8 MACs) — Serial → Log-Depth  ║")
    log("╚" + "═" * 58 + "╝")

    eg = EGraph()
    target = build_int4_mac_tile(eg, n_macs=8)
    log(f"  Initial: {len(eg.classes)} classes")

    t0 = time.time()
    iters = eg.saturate(FAST_RULES, max_iter=20)
    dt = time.time() - t0

    log(f"  Saturation: {iters} iters, {dt:.2f}s")
    analyze_target(eg, target, "int4 MAC Tile — After Core Rules")


def demo_scaling():
    """Demo 2: Scaling test — ADD chain width vs FPGA metrics."""
    hline("Demo 2: Scaling — ADD chain width vs FPGA metrics")

    log(f"  {'N':>4} {'Iters':>6} {'Classes':>8} {'Unions':>8} "
        f"{'Serial ns':>10} {'Tree ns':>10} {'Fmax MHz':>10} {'Time s':>8}")
    log(f"  {'─'*4} {'─'*6} {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

    for N in [4, 5, 6, 7, 8]:
        eg = EGraph()
        vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
        c = vs[0]
        for i in range(1, N):
            c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))

        serial_delay = (N - 1) * FPGA_DELAY_NS.get(AtomOp.ADD, 0.8)

        t0 = time.time()
        iters = eg.saturate(FAST_RULES, max_iter=15)
        dt = time.time() - t0

        cid = eg._canon(c)
        _, stats = eg.extract_fpga_optimal(cid)
        tree_delay = stats['delay_ns']
        fmax = stats['fmax_mhz']

        log(f"  {N:4d} {iters:6d} {len(eg.classes):8d} {eg.union_count:8d} "
            f"{serial_delay:10.2f} {tree_delay:10.2f} {fmax:10.0f} {dt:8.2f}")


def demo_mac_fpga():
    """Demo 3: MAC vs MUL+ADD — FPGA cost comparison."""
    hline("Demo 3: MAC vs MUL+ADD — FPGA cost comparison")

    eg = EGraph()
    w = eg.add(ENode(AtomOp.VAR, ("w",)))
    a = eg.add(ENode(AtomOp.VAR, ("a",)))
    acc = eg.add(ENode(AtomOp.ZERO, ()))

    mac = eg.add(ENode(AtomOp.MAC, (w, a, acc)))
    mul = eg.add(ENode(AtomOp.MUL, (w, a)))
    add_explicit = eg.add(ENode(AtomOp.ADD, (mul, acc)))

    eg.saturate(FAST_RULES, max_iter=10)

    cid = eg._canon(mac)
    ecls = eg.classes[cid]

    log(f"  Representations found: {len(ecls.nodes)}")
    for node in sorted(ecls.nodes, key=lambda n: (
            FPGA_LUT_COST.get(n.op, 0) + FPGA_DSP_COST.get(n.op, 0) * 8)):
        lut = FPGA_LUT_COST.get(node.op, 0)
        dsp = FPGA_DSP_COST.get(node.op, 0)
        delay = FPGA_DELAY_NS.get(node.op, 0)
        log(f"    {'🎯' if dsp else '🔧'} {node.op.name:10s} | LUT={lut:.1f} DSP={dsp} delay={delay:.1f}ns")

    _, stats = eg.extract_fpga_optimal(cid)
    log(f"  FPGA optimal: LUT={stats['lut']:.1f} DSP={stats['dsp']} "
        f"delay={stats['delay_ns']:.2f}ns fmax={stats['fmax_mhz']:.0f}MHz")


def demo_structural_discovery():
    """Demo 4: What did the e-graph actually discover?"""
    hline("Demo 4: Structural Discovery — What changed?")

    eg = EGraph()
    N = 8
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    serial = vs[0]
    for i in range(1, N):
        serial = eg.add(ENode(AtomOp.ADD, (serial, vs[i])))

    # Serial delay
    serial_delay_ns = (N - 1) * FPGA_DELAY_NS.get(AtomOp.ADD, 0.8)
    log(f"  Serial ADD chain (N={N}): depth {N-1}, delay {serial_delay_ns:.2f}ns, "
        f"fmax {1000/serial_delay_ns:.0f}MHz")

    eg.saturate(FAST_RULES, max_iter=20)
    cid = eg._canon(serial)
    _, stats = eg.extract_fpga_optimal(cid)

    tree_delay = stats['delay_ns']
    speedup = serial_delay_ns / tree_delay if tree_delay > 0 else float('inf')

    log(f"  Tree ADD (discovered):        depth ~{stats['lut_depth']:.0f}, "
        f"delay {tree_delay:.2f}ns, fmax {stats['fmax_mhz']:.0f}MHz")
    log(f"  Speedup: {speedup:.1f}×")
    log(f"  LUT cost: serial={N-1:.0f} → tree={stats['lut']:.1f} "
        f"({'same' if abs(stats['lut'] - (N-1)) < 0.5 else 'different'})")


def demo_pipeline_tradeoff():
    """Demo 5: Pipeline insertion — area vs frequency tradeoff."""
    hline("Demo 5: Pipeline Insertion — Area vs Frequency")

    eg = EGraph()
    target = build_int4_mac_tile(eg, n_macs=8)
    eg.saturate(FAST_RULES, max_iter=20)

    # Without pipeline
    cid = eg._canon(target)
    _, stats_no_pipe = eg.extract_fpga_optimal(cid)

    # With pipeline insertion
    eg2 = EGraph()
    target2 = build_int4_mac_tile(eg2, n_macs=8)
    eg2.saturate(FAST_RULES, max_iter=20)

    # Apply FPGA rules (DSP mapping + pipeline insertion)
    for rule in FPGA_RULES:
        rule(eg2)
    eg2.rebuild()

    cid2 = eg2._canon(target2)
    _, stats_with_pipe = eg2.extract_fpga_optimal(cid2)

    log(f"  {'':20} {'No Pipe':>12} {'With Pipe':>12}")
    log(f"  {'─'*20} {'─'*12} {'─'*12}")
    log(f"  {'LUTs':20} {stats_no_pipe['lut']:12.1f} {stats_with_pipe['lut']:12.1f}")
    log(f"  {'DSPs':20} {stats_no_pipe['dsp']:12.1f} {stats_with_pipe['dsp']:12.1f}")
    log(f"  {'FF':20} {stats_no_pipe['ff']:12.1f} {stats_with_pipe['ff']:12.1f}")
    log(f"  {'Delay (ns)':20} {stats_no_pipe['delay_ns']:12.2f} {stats_with_pipe['delay_ns']:12.2f}")
    log(f"  {'Fmax (MHz)':20} {stats_no_pipe['fmax_mhz']:12.0f} {stats_with_pipe['fmax_mhz']:12.0f}")
    log(f"  {'Cycles':20} {stats_no_pipe['cycles']:12.0f} {stats_with_pipe['cycles']:12.0f}")

    fmax_ratio = stats_with_pipe['fmax_mhz'] / stats_no_pipe['fmax_mhz'] if stats_no_pipe['fmax_mhz'] > 0 else 1
    log(f"\n  Pipeline impact: Fmax {fmax_ratio:.1f}× (at cost of {stats_with_pipe['ff'] - stats_no_pipe['ff']:.0f} extra FFs)")


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log()
    log("╔" + "═" * 58 + "╗")
    log("║     hwine — FPGA-Aware Meta-Operation e-Graph Demo     ║")
    log("║     int4 Quantization Hardware → Structural Opt        ║")
    log("╚" + "═" * 58 + "╝")

    t_start = time.time()

    demo_structural_discovery()
    demo_scaling()
    demo_mac_fpga()
    demo_int4_mac_tile()
    demo_pipeline_tradeoff()

    log(f"\n{'─'*60}")
    log(f"  Total: {time.time() - t_start:.2f}s")
    log()

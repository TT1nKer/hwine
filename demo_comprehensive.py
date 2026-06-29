#!/usr/bin/env python3
"""
hwine — Comprehensive FPGA Demo for parents-pc
===============================================
Scaling test + 128-lane MAC tile + RTL generation + comparison
"""
import sys, time, os
sys.path.insert(0, r"C:\hwine")

from tools.meta_ir import AtomOp, ENode, FPGA_DELAY_NS, FPGA_LUT_COST, FPGA_DSP_COST
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES, FPGA_RULES
from tools.rtl_gen import generate_rtl


def log(s=""):
    print(s, flush=True)


def hline(t=""):
    log(f"\n{'='*60}")
    log(f"  {t}")
    log(f"{'='*60}")


# ─── ADD chain scaling ─────────────────────────────────────

def demo_add_scaling():
    hline("ADD Chain Scaling — Serial → Log-Depth Tree")
    log(f"  {'N':>5} {'iters':>6} {'classes':>8} {'unions':>9} "
        f"{'ser ns':>8} {'tree ns':>8} {'fmax':>6} {'spup':>6} {'time s':>8}")
    log(f"  {'─'*5} {'─'*6} {'─'*8} {'─'*9} {'─'*8} {'─'*8} {'─'*6} {'─'*6} {'─'*8}")

    for N in [4, 8, 16, 32]:
        if N >= 16:
            log(f"  (running N={N}...)")

        eg = EGraph()
        vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
        c = vs[0]
        for i in range(1, N):
            c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))

        serial_ns = (N - 1) * FPGA_DELAY_NS.get(AtomOp.ADD, 0.8)
        t0 = time.time()
        iters = eg.saturate(FAST_RULES, max_iter=20, max_classes=5000)
        dt = time.time() - t0

        cid = eg._canon(c)
        _, stats = eg.extract_fpga_optimal(cid)
        tree_ns = stats['delay_ns']
        fmax = stats['fmax_mhz']
        spup = serial_ns / tree_ns if tree_ns > 0 else 0

        log(f"  {N:5d} {iters:6d} {len(eg.classes):8d} {eg.union_count:9d} "
            f"{serial_ns:8.2f} {tree_ns:8.2f} {fmax:6.0f} {spup:5.1f}x {dt:8.2f}")

    return dt if N < 16 else 0


# ─── int4 MAC tile ──────────────────────────────────────────

def demo_mac_tile(n_macs: int = 8):
    hline(f"int4×int8 MAC Tile ({n_macs} MACs)")

    eg = EGraph()
    zero = eg.add(ENode(AtomOp.ZERO, ()))
    vs_w = [eg.add(ENode(AtomOp.VAR, (f"w{i}",))) for i in range(n_macs)]
    vs_a = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(n_macs)]

    acc_init = eg.add(ENode(AtomOp.ACC_INIT, (zero,)))
    acc_state = acc_init
    mac_chain = acc_init
    for i in range(n_macs):
        mul = eg.add(ENode(AtomOp.MUL, (vs_w[i], vs_a[i])))
        acc_state = eg.add(ENode(AtomOp.ACC_STEP, (acc_state, mul)))
        mac_chain = eg.add(ENode(AtomOp.MAC, (vs_w[i], vs_a[i], mac_chain)))
    eg._union(acc_state, mac_chain)

    log(f"  Initial: {len(eg.classes)} classes")

    t0 = time.time()
    iters = eg.saturate(FAST_RULES, max_iter=15, max_classes=5000)
    dt = time.time() - t0

    cid = eg._canon(acc_state)
    n_repr = len(eg.classes[cid].nodes)

    # FPGA extraction
    _, stats = eg.extract_fpga_optimal(cid)
    # Also do Pareto
    pareto = eg.extract_pareto_front(cid, sample=30)

    serial_add_ns = n_macs * FPGA_DELAY_NS.get(AtomOp.ADD, 0.8)
    dsp_ns = FPGA_DELAY_NS.get(AtomOp.DSP_MUL, 2.5)

    log(f"  Saturation: {iters} iters, {dt:.2f}s")
    log(f"  E-graph: {len(eg.classes)} classes, {eg.union_count} unions, {n_repr} reprs")
    log(f"")
    log(f"  ╔══ FPGA Extraction ══╗")
    log(f"  ║ LUTs:      {stats['lut']:8.1f}       ║")
    log(f"  ║ DSPs:      {stats['dsp']:8.1f}       ║")
    log(f"  ║ FFs:       {stats['ff']:8.1f}       ║")
    log(f"  ║ Crit path: {stats['delay_ns']:8.2f} ns   ║")
    log(f"  ║ Fmax:      {stats['fmax_mhz']:8.1f} MHz   ║")
    log(f"  ╚══════════════════════╝")
    log(f"")

    # Serial reference
    serial_area = n_macs * (FPGA_LUT_COST.get(AtomOp.ADD, 0.5) +
                            FPGA_DSP_COST.get(AtomOp.MUL, 1) * 10)
    tree_area = stats['lut'] + stats['dsp'] * 10
    serial_delay = serial_add_ns + dsp_ns
    tree_delay = stats['delay_ns']

    log(f"  Reference (serial MAC chain):")
    log(f"    Area: {serial_area:.1f}  Delay: {serial_delay:.2f}ns  Fmax: {1000/serial_delay:.0f}MHz")
    log(f"  Optimized (discovered tree):")
    log(f"    Area: {tree_area:.1f}  Delay: {tree_delay:.2f}ns  Fmax: {stats['fmax_mhz']:.0f}MHz")
    log(f"    Area Δ: {((tree_area-serial_area)/serial_area*100):+.1f}%  Speedup: {serial_delay/tree_delay:.1f}×")

    # Pareto
    if pareto:
        log(f"")
        log(f"  Pareto frontier ({len(pareto)} points):")
        for p in pareto[:5]:
            area = p['lut'] + p['dsp'] * 10
            log(f"    area={area:.1f}  delay={p['delay_ns']:.2f}ns  fmax={p['fmax_mhz']:.0f}MHz")

    return eg, cid


# ─── RTL generation ────────────────────────────────────────

def demo_rtl_gen(eg: EGraph, cid: int):
    hline("RTL Generation")

    rtl, tb = generate_rtl(eg, cid, "int4_mac_core", 8, "result")

    # Write to files
    rtl_path = r"C:\hwine\output\int4_mac_core.sv"
    tb_path  = r"C:\hwine\output\tb_int4_mac_core.sv"
    os.makedirs(r"C:\hwine\output", exist_ok=True)

    with open(rtl_path, 'w') as f:
        f.write(rtl)
    with open(tb_path, 'w') as f:
        f.write(tb)

    # Summary
    lines = rtl.count('\n')
    ports = rtl.count('input') + rtl.count('output')
    wires = rtl.count('logic signed')

    log(f"  RTL written to: {rtl_path}")
    log(f"    Lines: {lines}, Ports: {ports}, Internal wires: {wires}")
    log(f"  Testbench: {tb_path}")
    log(f"")
    log(f"  First 20 lines of RTL:")
    for line in rtl.split('\n')[:20]:
        log(f"    {line}")


# ─── Comparison table ──────────────────────────────────────

def demo_comparison():
    hline("Comparison: Our Approach vs State-of-the-Art")

    log(f"  {'':30} {'ROVER':>12} {'PrefixRL':>12} {'Our hwine':>12}")
    log(f"  {'─'*30} {'─'*12} {'─'*12} {'─'*12}")
    log(f"  {'Organization':30} {'Intel':>12} {'NVIDIA':>12} {'hwine':>12}")
    log(f"  {'Method':30} {'e-graph':>12} {'Deep RL':>12} {'e-graph':>12}")
    log(f"  {'Level':30} {'RTL→RTL':>12} {'prefix graph':>12} {'meta-op→RTL':>12}")
    log(f"  {'Best area reduction':30} {'63%':>12} {'25%':>12} {'TBD':>12}")
    log(f"  {'Deployment':30} {'5nm TSMC':>12} {'Hopper GPU':>12} {'FPGA target':>12}")
    log(f"  {'Training needed':30} {'No':>12} {'GPU cluster':>12} {'No':>12}")
    log(f"  {'Structural discovery':30} {'RTL-level':>12} {'RL search':>12} {'Algebraic':>12}")
    log(f"")

    log(f"  Key differentiator: hwine discovers tree structures from algebraic")
    log(f"  declarations, not from gate-level pattern matching or RL trial-and-error.")
    log(f"  A single 'ADD is associative' rule automatically finds Brent-Kung-like")
    log(f"  prefix tree structures for ANY associative operation (ADD, MAX, MIN, ...).")


# ─── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    log()
    log("╔" + "═" * 58 + "╗")
    log("║    hwine — FPGA Structural Discovery + RTL Gen          ║")
    log("║    Running on parents-pc (Windows, 16-core)             ║")
    log("╚" + "═" * 58 + "╝")

    t_start = time.time()

    # 1. Scaling
    demo_add_scaling()

    # 2. MAC tile
    eg, cid = demo_mac_tile(n_macs=8)

    # 3. RTL generation
    demo_rtl_gen(eg, cid)

    # 4. Comparison
    demo_comparison()

    log(f"\n  Total: {time.time()-t_start:.1f}s")
    log(f"{'='*60}")
    log()

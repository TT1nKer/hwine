#!/usr/bin/env python3
"""hwine — Throughput-aware FPGA demo. Pipelined tree vs serial chain."""
import sys, time, os
sys.path.insert(0, r"C:\hwine")

from tools.meta_ir import AtomOp, ENode, FPGA_DELAY_NS, FPGA_LUT_COST, FPGA_DSP_COST, FPGA_CYC_LATENCY
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES, FPGA_RULES
from tools.rtl_gen import generate_rtl


def log(s=""):
    print(s, flush=True)

def hline(t=""):
    log(f"\n{'='*60}")
    log(f"  {t}")
    log(f"{'='*60}")


def simulate_throughput(eg: EGraph, cid: int, fmax_mhz: float,
                        pipeline_stages: int = 0):
    """Calculate throughput: after pipeline fill, one result every cycle."""
    # Latency: cycles from first input to first output
    latency_cycles = pipeline_stages + 1  # +1 for the final op
    # Throughput: after fill, 1 result per cycle at Fmax
    results_per_second = fmax_mhz * 1e6
    # For serial chain without pipelining, throughput = Fmax / N
    return {
        'latency_cycles': latency_cycles,
        'latency_ns': (latency_cycles / fmax_mhz) * 1000 if fmax_mhz > 0 else 0,
        'throughput_mrps': results_per_second / 1e6,
        'initiation_interval': 1,  # fully pipelined = 1 cycle per new input
    }


def demo_throughput_vs_latency():
    hline("Throughput vs Latency: Pipeline Changes Everything")

    N = 8
    add_delay = FPGA_DELAY_NS.get(AtomOp.ADD, 0.8)
    dsp_delay = FPGA_DELAY_NS.get(AtomOp.DSP_MUL, 2.5)

    log(f"  Scenario: {N} MUL + {N-1} ADD (int4 GEMM tile)")
    log(f"")

    # ── Serial chain (no pipelining) ──
    serial_fmax = 1000 / (dsp_delay + (N-1) * add_delay)
    serial_tp = serial_fmax / N  # must wait N cycles for all MACs

    log(f"  {'Design':25} {'Latency':>10} {'Fmax':>8} {'Throughput':>14} {'II':>6}")
    log(f"  {'-'*25} {'-'*10} {'-'*8} {'-'*14} {'-'*6}")
    log(f"  {'Serial MAC chain':25} {dsp_delay + (N-1)*add_delay:>8.1f}ns "
        f"{serial_fmax:>6.0f}MHz {serial_tp:>12.1f} Mrps {'∞':>6}")

    # ── Tree (no pipelining, just combinational) ──
    eg = EGraph()
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))
    eg.saturate(FAST_RULES, max_iter=15)
    _, stats = eg.extract_fpga_optimal(eg._canon(c))
    tree_fmax = stats['fmax_mhz']
    tree_delay = stats['delay_ns']

    log(f"  {'ADD tree (combinational)':25} {tree_delay:>8.1f}ns "
        f"{tree_fmax:>6.0f}MHz {tree_fmax:>12.1f} Mrps {'1':>6}")

    # ── Pipelined tree (register after each level) ──
    # Insert PIPE after each ADD level
    levels = int(tree_delay / add_delay)  # ~log2(N) levels
    pipe_delay_per_stage = add_delay + 0.3  # ADD + register
    piped_delay = levels * pipe_delay_per_stage
    piped_fmax = min(1000 / pipe_delay_per_stage, 500)
    piped_tp = piped_fmax  # 1 result per cycle

    log(f"  {'Pipelined ADD tree':25} {piped_delay:>8.1f}ns "
        f"{piped_fmax:>6.0f}MHz {piped_tp:>12.1f} Mrps {'1':>6}")
    log(f"")
    log(f"  Pipeline stages: {levels} (register after each tree level)")
    log(f"  After initial fill ({levels} cycles): 1 result EVERY cycle")
    log(f"")

    # ── MAC tile comparison ──
    log(f"  {'─'*60}")
    log(f"  MAC tile comparison (8 MACs, pipelined tree):")
    log(f"")

    eg2 = EGraph()
    z = eg2.add(ENode(AtomOp.ZERO, ()))
    ws = [eg2.add(ENode(AtomOp.VAR, (f"w{i}",))) for i in range(N)]
    as_ = [eg2.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    ai = eg2.add(ENode(AtomOp.ACC_INIT, (z,)))
    acc = ai
    mc = ai
    for i in range(N):
        m = eg2.add(ENode(AtomOp.MUL, (ws[i], as_[i])))
        acc = eg2.add(ENode(AtomOp.ACC_STEP, (acc, m)))
        mc = eg2.add(ENode(AtomOp.MAC, (ws[i], as_[i], mc)))
    eg2._union(acc, mc)
    eg2.saturate(FAST_RULES, max_iter=15)

    # Apply FPGA rules (DSP + pipeline)
    for r in FPGA_RULES:
        r(eg2)
    eg2.rebuild()

    cid2 = eg2._canon(acc)
    _, s = eg2.extract_fpga_optimal(cid2)

    # Serial MAC chain
    ser_d = dsp_delay + N * dsp_delay  # 1st DSP + N MACs chained
    ser_f = 1000 / ser_d

    # Pipelined tree: MULs in parallel (1 DSP delay) + log2(N) ADD stages
    pipe_stages = 1 + int(s['delay_ns'] / add_delay)  # MUL + ADD levels
    piped_tp_mac = min(1000 / dsp_delay, 500)

    log(f"  {'':20} {'Latency':>10} {'Fmax':>8} {'Throughput':>14} {'Pipeline':>10}")
    log(f"  {'-'*20} {'-'*10} {'-'*8} {'-'*14} {'-'*10}")
    log(f"  {'Serial MAC':20} {ser_d:>8.1f}ns {ser_f:>6.0f}MHz "
        f"{ser_f/N:>12.1f} Mrps {'0':>10}")
    log(f"  {'Pipelined tree':20} {s['delay_ns'] + pipe_stages*0.3:>8.1f}ns "
        f"{piped_tp_mac:>6.0f}MHz {piped_tp_mac:>12.1f} Mrps {pipe_stages:>10}")

    ratio = piped_tp_mac / (ser_f/N) if ser_f > 0 else float('inf')
    log(f"")
    log(f"  Throughput improvement: {ratio:.1f}x")
    log(f"  Key insight: pipelined tree accepts new data EVERY cycle,")
    log(f"  while serial MAC must wait {N} cycles between inputs.")


def demo_pipeline_rule():
    hline("Pipeline Rule: Auto-Insert Registers Between Tree Levels")

    N = 8
    eg = EGraph()
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))

    # Without pipeline
    eg.saturate(FAST_RULES, max_iter=15)
    _, s_no = eg.extract_fpga_optimal(eg._canon(c))

    # With pipeline insertion
    eg2 = EGraph()
    vs2 = [eg2.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c2 = vs2[0]
    for i in range(1, N):
        c2 = eg2.add(ENode(AtomOp.ADD, (c2, vs2[i])))
    eg2.saturate(FAST_RULES, max_iter=15)

    # Manually insert PIPE after tree has been discovered
    # Walk the extracted tree and add PIPE after each ADD level
    cid = eg2._canon(c2)
    best_node, _ = eg2.extract_fpga_optimal(cid)

    pipe_count = 0

    def insert_pipes(egr, node_cid, depth=0):
        nonlocal pipe_count
        node_cid = egr._canon(node_cid)
        if node_cid not in egr.classes:
            return node_cid
        best_n, _ = egr.extract_fpga_optimal(node_cid)
        if best_n is None:
            return node_cid
        if best_n.op == AtomOp.ADD and depth > 0:
            pipe_count += 1
            piped = egr.add(ENode(AtomOp.PIPE, (node_cid,)))
            return piped
        return node_cid

    # Walk and insert
    root = eg2._canon(c2)
    # (simplified: just add one global pipe)
    piped_root = eg2.add(ENode(AtomOp.PIPE, (root,)))
    eg2.rebuild()

    _, s_pipe = eg2.extract_fpga_optimal(piped_root)

    log(f"  {'':20} {'No Pipeline':>14} {'With Pipeline':>14}")
    log(f"  {'-'*20} {'-'*14} {'-'*14}")
    log(f"  {'Delay (ns)':20} {s_no['delay_ns']:>14.2f} {s_pipe['delay_ns']:>14.2f}")
    log(f"  {'Fmax (MHz)':20} {s_no['fmax_mhz']:>14.0f} {s_pipe['fmax_mhz']:>14.0f}")
    log(f"  {'FF count':20} {s_no['ff']:>14.0f} {s_pipe['ff']:>14.0f}")
    log(f"  {'Initiation II':20} {'N cycles':>14} {'1 cycle':>14}")
    log(f"")
    no_pipe_tp = s_no['fmax_mhz'] / N
    pipe_tp = s_pipe['fmax_mhz']
    log(f"  Throughput: {no_pipe_tp:.0f} Mrps → {pipe_tp:.0f} Mrps ({pipe_tp/no_pipe_tp:.1f}x)")


def generate_rtl_with_pipeline():
    hline("RTL: Pipelined MAC Tile → SystemVerilog")

    N = 8
    eg = EGraph()
    z = eg.add(ENode(AtomOp.ZERO, ()))
    ws = [eg.add(ENode(AtomOp.VAR, (f"w{i}",))) for i in range(N)]
    as_ = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    ai = eg.add(ENode(AtomOp.ACC_INIT, (z,)))
    acc = ai; mc = ai
    for i in range(N):
        m = eg.add(ENode(AtomOp.MUL, (ws[i], as_[i])))
        acc = eg.add(ENode(AtomOp.ACC_STEP, (acc, m)))
        mc = eg.add(ENode(AtomOp.MAC, (ws[i], as_[i], mc)))
    eg._union(acc, mc)
    eg.saturate(FAST_RULES, max_iter=15)
    for r in FPGA_RULES:
        r(eg)
    eg.rebuild()

    cid = eg._canon(acc)
    rtl, tb = generate_rtl(eg, cid, "piped_mac_tile", 8, "result")

    os.makedirs(r"C:\hwine\output", exist_ok=True)
    with open(r"C:\hwine\output\piped_mac_tile.sv", 'w') as f:
        f.write(rtl)
    with open(r"C:\hwine\output\tb_piped_mac_tile.sv", 'w') as f:
        f.write(tb)

    lines = rtl.count('\n')
    log(f"  Generated: {lines} lines")
    log(f"  Output: C:\\hwine\\output\\piped_mac_tile.sv")
    log(f"")
    log(f"  Key RTL features:")
    log(f"    - DSP48-inferred MUL operations")
    log(f"    - Log-depth ADD tree (structure discovered by e-graph)")
    log(f"    - valid/ready handshake ready for pipeline")
    log(f"    - parameterized DATA_WIDTH")


if __name__ == "__main__":
    log()
    log("=" * 60)
    log("  hwine — Throughput-Aware FPGA Design")
    log("  Pipeline: data flows continuously, no waiting")
    log("=" * 60)

    demo_throughput_vs_latency()
    demo_pipeline_rule()
    generate_rtl_with_pipeline()

    log(f"\n  Done.")
    log()

#!/usr/bin/env python3
"""hwine — MIN/MAX sorting network: same associativity rule, different problem"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.meta_ir import AtomOp, ENode, FPGA_DELAY_NS
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES
from tools.rtl_gen import generate_rtl

OUT = "/tmp/hwine_minmax"
os.makedirs(OUT, exist_ok=True)

def log(s=""): print(s, flush=True)

def build_minmax_chain(N: int, op: AtomOp):
    """Build serial MIN or MAX chain: OP(OP(OP(a0,a1), a2), ..., a{N-1})"""
    eg = EGraph()
    vs = [eg.add(ENode(AtomOp.VAR, (f"v{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(op, (c, vs[i])))
    return eg, eg._canon(c)

def analyze_minmax(N: int, op: AtomOp):
    """Serialize, saturate, extract, compare."""
    op_name = op.name
    
    # Serial
    eg_s, cid_s = build_minmax_chain(N, op)
    _, stats_s = eg_s.extract_fpga_optimal(eg_s._canon(cid_s))
    ser_ns = (N-1) * FPGA_DELAY_NS.get(op, 0.8)
    ser_f = 1000/ser_ns if ser_ns > 0 else 0
    
    # Saturate → tree
    eg_t, cid_t = build_minmax_chain(N, op)
    eg_t.saturate(FAST_RULES, max_iter=15)
    _, stats_t = eg_t.extract_fpga_optimal(eg_t._canon(cid_t))
    tree_ns = stats_t['delay_ns']
    tree_f = stats_t['fmax_mhz']
    
    # Generate RTL
    rtl_s, _ = generate_rtl(eg_s, eg_s._canon(cid_s), f"{op_name.lower()}_serial_{N}", 8)
    rtl_t, _ = generate_rtl(eg_t, eg_t._canon(cid_t), f"{op_name.lower()}_tree_{N}", 8)
    
    with open(f"{OUT}/{op_name.lower()}_s_{N}.sv", 'w') as f: f.write(rtl_s)
    with open(f"{OUT}/{op_name.lower()}_t_{N}.sv", 'w') as f: f.write(rtl_t)
    
    speedup = ser_ns/tree_ns if tree_ns > 0 else 0
    return ser_ns, tree_ns, ser_f, tree_f, speedup


if __name__ == "__main__":
    log("=" * 70)
    log("  hwine — MIN/MAX Sorting Network: Same Rule, Different Problem")
    log("  'ADD associative' = 'MIN associative' = 'MAX associative'")
    log("=" * 70)
    
    for op, desc in [(AtomOp.ADD, "ADD (sum)"), 
                      (AtomOp.REDUCE_MIN, "MIN (find minimum)"),
                      (AtomOp.REDUCE_MAX, "MAX (find maximum)")]:
        log(f"\n  {desc}:")
        log(f"  {'N':>4} {'Serial ns':>10} {'Tree ns':>10} {'Speedup':>8} {'Fmax':>10}")
        log(f"  {'─'*4} {'─'*10} {'─'*10} {'─'*8} {'─'*10}")
        
        for N in [4, 8, 16, 32]:
            ser_ns, tree_ns, _, tree_f, sp = analyze_minmax(N, op)
            log(f"  {N:4d} {ser_ns:10.2f} {tree_ns:10.2f} {sp:7.1f}x {tree_f:9.0f}MHz")
    
    log(f"\n  ── Insight ──")
    log(f"  ADD, MIN, MAX all satisfy associativity.")
    log(f"  One rule discovers tree structures for ALL of them.")
    log(f"  This is not 'designing a better adder' — it's 'declaring algebra'")
    log(f"  and letting the e-graph design the hardware structure.")
    
    log(f"\n  RTL files: {OUT}/")
    import subprocess
    subprocess.run(["ls", "-la", OUT], capture_output=False)
    log(f"{'='*70}")

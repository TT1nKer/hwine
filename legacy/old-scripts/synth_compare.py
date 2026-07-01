#!/usr/bin/env python3
"""hwine — Generate + Synthesize: Serial vs Tree RTL comparison"""
import sys, os, subprocess, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.meta_ir import AtomOp, ENode
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES
from tools.rtl_gen import generate_rtl


OUT_DIR = "/tmp/hwine_synth"
os.makedirs(OUT_DIR, exist_ok=True)


def log(s=""):
    print(s, flush=True)


def write_rtl(rtl_str: str, filename: str) -> str:
    path = os.path.join(OUT_DIR, filename)
    with open(path, 'w') as f:
        f.write(rtl_str)
    return path


def synth_with_yosys(rtl_path: str, top: str) -> dict:
    """Run Yosys synthesis, return cell count."""
    script = f"""
read_verilog -sv {rtl_path}
synth -top {top}
stat
"""
    yosys_path = os.path.join(OUT_DIR, f"{top}.ys")
    with open(yosys_path, 'w') as f:
        f.write(script)

    try:
        result = subprocess.run(
            ["yosys", "-s", yosys_path],
            capture_output=True, text=True, timeout=120
        )
        cells = 0
        for line in (result.stdout + result.stderr).split('\n'):
            # Parse "## cells" from final stat line
            stripped = line.strip()
            parts = stripped.split()
            if len(parts) == 2 and parts[1] == 'cells':
                try:
                    cells = max(cells, int(parts[0]))
                except ValueError:
                    pass
            # Parse ABC RESULTS lines
            if stripped.startswith('ABC RESULTS'):
                for token in parts:
                    if token.isdigit():
                        try:
                            cells += int(token)
                        except ValueError:
                            pass
        return {"num_cells": cells}
        return {"num_cells": cells, "raw": ""}
    except Exception as e:
        return {"error": str(e), "num_cells": -1}


def build_serial_chain(N: int = 8) -> tuple[EGraph, int, str]:
    """Build serial ADD chain. Returns (eg, cid, rtl_code)."""
    eg = EGraph()
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))
    rtl, _ = generate_rtl(eg, eg._canon(c), f"serial_add_{N}", 8)
    return eg, eg._canon(c), rtl


def build_tree_add(N: int = 8) -> tuple[EGraph, int, str]:
    """Build serial chain → saturate → extract tree. Returns (eg, cid, rtl_code)."""
    eg = EGraph()
    vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg.add(ENode(AtomOp.ADD, (c, vs[i])))
    eg.saturate(FAST_RULES, max_iter=20)
    _, stats = eg.extract_fpga_optimal(eg._canon(c))
    rtl, _ = generate_rtl(eg, eg._canon(c), f"tree_add_{N}", 8)
    return eg, eg._canon(c), rtl, stats


def build_serial_mac(N: int = 8) -> tuple[EGraph, int, str]:
    """Build serial MAC chain."""
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
    rtl, _ = generate_rtl(eg, eg._canon(acc), f"serial_mac_{N}", 8)
    return eg, eg._canon(acc), rtl


def build_tree_mac(N: int = 8) -> tuple[EGraph, int, str, dict]:
    """Build serial MAC → saturate → extract tree."""
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

    # Apply FPGA rules
    from tools.meta_rewrite import FPGA_RULES
    for r in FPGA_RULES:
        r(eg)
    eg.rebuild()

    _, stats = eg.extract_fpga_optimal(eg._canon(acc))
    rtl, _ = generate_rtl(eg, eg._canon(acc), f"tree_mac_{N}", 8)
    return eg, eg._canon(acc), rtl, stats


if __name__ == "__main__":
    log("=" * 65)
    log("  hwine — RTL Synthesis Comparison: Serial vs Tree")
    log("  Target: Yosys + generic stdcells")
    log("=" * 65)

    for N in [4, 8]:
        log(f"\n{'─'*65}")
        log(f"  N = {N} inputs")
        log(f"{'─'*65}")

        # ── ADD comparison ──
        log(f"\n  --- ADD chain ({N} inputs) ---")

        # Serial
        eg_s, cid_s, rtl_s = build_serial_chain(N)
        rtl_s_path = write_rtl(rtl_s, f"serial_add_{N}.sv")
        synth_s = synth_with_yosys(rtl_s_path, f"serial_add_{N}")
        cells_s = synth_s.get("num_cells", -1)

        # Tree
        eg_t, cid_t, rtl_t, stats_t = build_tree_add(N)
        rtl_t_path = write_rtl(rtl_t, f"tree_add_{N}.sv")
        synth_t = synth_with_yosys(rtl_t_path, f"tree_add_{N}")
        cells_t = synth_t.get("num_cells", -1)

        log(f"  Serial ADD: {cells_s} cells")
        log(f"  Tree   ADD: {cells_t} cells  (depth {stats_t['delay_ns']:.2f}ns)")
        log(f"  Cell Δ: {cells_t - cells_s:+d}  ({'' if cells_t <= cells_s else '⚠️ '}tree overhead)")

        # ── MAC comparison ──
        log(f"\n  --- MAC tile ({N} MACs) ---")

        eg_ms, cid_ms, rtl_ms = build_serial_mac(N)
        rtl_ms_path = write_rtl(rtl_ms, f"serial_mac_{N}.sv")
        synth_ms = synth_with_yosys(rtl_ms_path, f"serial_mac_{N}")
        cells_ms = synth_ms.get("num_cells", -1)

        eg_mt, cid_mt, rtl_mt, stats_mt = build_tree_mac(N)
        rtl_mt_path = write_rtl(rtl_mt, f"tree_mac_{N}.sv")
        synth_mt = synth_with_yosys(rtl_mt_path, f"tree_mac_{N}")
        cells_mt = synth_mt.get("num_cells", -1)

        log(f"  Serial MAC: {cells_ms} cells")
        log(f"  Tree   MAC: {cells_mt} cells  (depth {stats_mt['delay_ns']:.2f}ns)")
        log(f"  Cell Δ: {cells_mt - cells_ms:+d}")

    log(f"\n{'─'*65}")
    log(f"  RTL files: {OUT_DIR}/")
    log(f"    $(ls {OUT_DIR}/*.sv 2>/dev/null)")
    log()

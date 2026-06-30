#!/usr/bin/env python3
"""Generate Vivado HLS baseline kernels and compare against hwine results.

Usage:
    python3 run_hls.py --kernel fir --taps 8
    python3 run_hls.py --kernel dct
    python3 run_hls.py --all

Prerequisites:
    - Vivado HLS 2026.1 in PATH
    - hwine-rs built (`cargo build --release` in hwine-rs/)
"""

import argparse
import subprocess
import os
import sys

HLS_TEMPLATES = {
    "fir": """
#include <ap_int.h>

void fir(ap_int<16> x[%d], ap_int<16> *y) {
    const ap_int<16> coeff[%d] = {%s};
    ap_int<32> acc = 0;
    for (int i = 0; i < %d; i++) {
        acc += x[i] * coeff[i];
    }
    *y = acc;
}
""",
    "gemm": """
#include <ap_int.h>

void dot_product(ap_int<16> a[%d], ap_int<16> b[%d], ap_int<32> *y) {
    ap_int<32> acc = 0;
    for (int i = 0; i < %d; i++) {
        acc += a[i] * b[i];
    }
    *y = acc;
}
""",
    "dct": """
#include <ap_int.h>

void dct8(ap_int<16> x[8], ap_int<16> y[8]) {
    const ap_int<16> coeff[8] = {181, 251, 213, 142, 256, 107, 71, 25};
    for (int k = 0; k < 8; k++) {
        ap_int<32> acc = 0;
        for (int n = 0; n < 8; n++) {
            acc += x[n] * coeff[(n*k) %% 8];
        }
        y[k] = acc >> 8;
    }
}
""",
}

def generate_hls(kernel: str, tap_count: int = 8) -> str:
    return _gen(kernel, tap_count)

def _gen(kernel: str, tap_count: int = 8) -> str:
    """Generate C++ HLS kernel source."""
    if kernel == "fir":
        coeffs = [3, 7, 13, 5, 11, 9, 2, 6, 14, 4, 10, 8]
        actual_taps = min(tap_count, len(coeffs))
        coeff_str = ", ".join(str(coeffs[i % len(coeffs)]) for i in range(actual_taps))
        return HLS_TEMPLATES["fir"] % (actual_taps, actual_taps, coeff_str, actual_taps)
    elif kernel == "gemm":
        return HLS_TEMPLATES["gemm"] % (tap_count, tap_count, tap_count)
    elif kernel == "dct":
        return HLS_TEMPLATES["dct"]
    else:
        raise ValueError(f"Unknown kernel: {kernel}")

HLS_TCL_TEMPLATE = """
# Auto-generated Vivado HLS synthesis script for {kernel}
open_project {kernel}_hls
set_top {top}
add_files {kernel}_hls.cpp
open_solution solution1
set_part {part}
create_clock -period {period}
csynth_design
export_design -format ip_catalog
exit
"""

def generate_hls_tcl(kernel: str, top: str, part: str = "xc7vx485tffg1761-2", period: str = "3.3") -> str:
    return HLS_TCL_TEMPLATE.format(kernel=kernel, top=top, part=part, period=period)

def parse_csynth_rpt(kernel: str) -> dict:
    """Parse Vivado HLS csynth.rpt and extract utilization + latency.
    Returns dict with: LUT, FF, DSP, BRAM, latency_min, latency_max, clock_ns.
    """
    rpt_path = os.path.join(f"{kernel}_hls", "solution1", "syn", "report", f"{kernel}_csynth.rpt")
    if not os.path.exists(rpt_path):
        print(f"Warning: {rpt_path} not found — run Vivado HLS first")
        return {}
    # Simple regex parsing of Vivado HLS synthesis report
    import re
    result = {}
    with open(rpt_path) as f:
        text = f.read()
    # Utilization
    lut_m = re.search(r"LUT\s+\|\s+(\d+)", text)
    ff_m = re.search(r"FF\s+\|\s+(\d+)", text)
    dsp_m = re.search(r"DSP48E\s+\|\s+(\d+)", text)
    bram_m = re.search(r"BRAM_18K\s+\|\s+(\d+)", text)
    # Latency
    lat_m = re.search(r"Latency.*?(\d+)\s*-\s*(\d+)", text, re.DOTALL)
    # Clock
    clk_m = re.search(r"Target\s+(\d+\.?\d*)", text)
    if lut_m: result["LUT"] = int(lut_m.group(1))
    if ff_m: result["FF"] = int(ff_m.group(1))
    if dsp_m: result["DSP"] = int(dsp_m.group(1))
    if bram_m: result["BRAM"] = int(bram_m.group(1))
    if lat_m: result["latency"] = f"{lat_m.group(1)}-{lat_m.group(2)}"
    if clk_m: result["clock_ns"] = float(clk_m.group(1))
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", choices=["fir", "gemm", "dct"], default="fir")
    parser.add_argument("--taps", type=int, default=8)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--csv", default="paper/data/hls_baseline.csv", help="Output CSV path")
    args = parser.parse_args()

    out_dir = "benchmarks/hls_baseline"
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs("paper/data", exist_ok=True)

    kernels = ["fir", "gemm", "dct"] if args.all else [args.kernel]
    csv_rows = []

    tops = {"fir": "fir", "gemm": "dot_product", "dct": "dct8"}
    parts = {"fir": "xc7vx485tffg1761-2", "gemm": "xc7vx485tffg1761-2", "dct": "xc7vx485tffg1761-2"}

    for kernel in kernels:
        taps = args.taps
        source = generate_hls(kernel, taps)
        top = tops[kernel]
        part = parts[kernel]

        src_file = os.path.join(out_dir, f"{kernel}_hls.cpp")
        with open(src_file, "w") as f:
            f.write(source)
        print(f"Generated: {src_file}")

        tcl_src = generate_hls_tcl(kernel, top, part)
        tcl_file = os.path.join(out_dir, f"synth_{kernel}_hls.tcl")
        with open(tcl_file, "w") as f:
            f.write(tcl_src)
        print(f"Generated: {tcl_file}")

        # Attempt to parse existing csynth.rpt (if previously run)
        report = parse_csynth_rpt(kernel)
        if report:
            csv_rows.append({
                "kernel": kernel,
                "taps": taps,
                "tool": "Vivado HLS",
                **report,
            })
            print(f"  Report: LUT={report.get('LUT','?')} DSP={report.get('DSP','?')} FF={report.get('FF','?')} latency={report.get('latency','?')}")
        else:
            print(f"  Run: vitis_hls -f {tcl_file} to synthesize (Vivado HLS)")
            csv_rows.append({
                "kernel": kernel,
                "taps": taps,
                "tool": "Vivado HLS",
                "LUT": "TBD",
                "FF": "TBD",
                "DSP": "TBD",
                "BRAM": "TBD",
                "latency": "TBD",
                "clock_ns": "3.3",
                "note": "Run Vivado HLS to fill",
            })

    # Write CSV
    import csv
    fieldnames = ["kernel", "taps", "tool", "LUT", "FF", "DSP", "BRAM", "latency", "clock_ns", "note"]
    with open(args.csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nCSV: {args.csv} ({len(csv_rows)} rows)")

if __name__ == "__main__":
    main()

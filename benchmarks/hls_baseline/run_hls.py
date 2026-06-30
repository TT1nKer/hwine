#!/usr/bin/env python3
"""Vivado HLS baseline runner.

Generates HLS project TCL files, invokes vitis_hls, and parses synthesis
reports to produce a CSV comparison against hwine e-graph results.

Requires: Vivado HLS (vitis_hls) on PATH or VITIS_HLS_PATH env var.
"""

import subprocess
import sys
import os
import argparse
import csv
import tempfile
from pathlib import Path

KERNELS_DIR = Path(__file__).parent / "kernels"

# Map of benchmark → (source file, top function, expected results)
BENCHMARKS = {
    "fir6": ("fir_streaming.cpp", "fir_streaming"),
    "fir20": ("fir_streaming.cpp", "fir_streaming"),
    "fir41": ("fir_streaming.cpp", "fir_streaming"),
    "dct8": ("dct8.cpp", "dct8"),
    "gemm_dot8": ("gemm_dot8.cpp", "gemm_dot8"),
    "fft_butterfly": ("fft_butterfly.cpp", "fft_butterfly"),
}


def generate_hls_tcl(top_fn, src_file, clock_mhz, part, out_dir):
    """Generate a Vivado HLS run.tcl script."""
    tcl = f"""# Auto-generated Vivado HLS project script
open_project -reset hls_baseline
set_top {top_fn}
add_files {src_file}
open_solution -reset solution1
set_part {{{part}}}
create_clock -period {1000.0 / clock_mhz:.2f} -name default
csynth_design
export_design -format ip_catalog -output {out_dir}
exit
"""
    return tcl


def run_hls(top_fn, src_file, clock_mhz, part, work_dir):
    """Run Vivado HLS synthesis and return resource utilization."""
    tcl = generate_hls_tcl(top_fn, src_file, clock_mhz, part, work_dir)
    tcl_path = work_dir / "run_hls.tcl"
    tcl_path.write_text(tcl)

    vitis = os.environ.get("VITIS_HLS_PATH", "vitis_hls")
    result = subprocess.run(
        [vitis, "-f", str(tcl_path)],
        cwd=work_dir,
        capture_output=True,
        text=True,
    )

    # Parse csynth.rpt for resource utilization
    rpt_path = work_dir / "solution1" / "syn" / "report" / f"{top_fn}_csynth.rpt"
    if not rpt_path.exists():
        return None

    rpt_text = rpt_path.read_text()
    lut = _extract_num(rpt_text, "CLB LUTs")
    ff = _extract_num(rpt_text, "FFs")
    dsp = _extract_num(rpt_text, "DSP48E")
    latency = _extract_num(rpt_text, "Latency (cycles)")
    clock = _extract_num(rpt_text, "Target Clock Period")

    return {
        "LUT": lut,
        "FF": ff,
        "DSP": dsp,
        "Latency_cycles": latency,
        "Clock_MHz": clock_mhz if clock is None else 1000.0 / clock,
    }


def _extract_num(text, keyword):
    """Extract a number from a report text line containing keyword."""
    for line in text.split("\n"):
        if keyword in line:
            parts = line.split()
            for p in parts:
                try:
                    return float(p.replace(",", ""))
                except ValueError:
                    continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Vivado HLS baseline runner")
    parser.add_argument("--all", action="store_true", help="Run all benchmarks")
    parser.add_argument("--bench", type=str, nargs="+", help="Specific benchmarks to run")
    parser.add_argument("--clock", type=float, default=308.0, help="Target clock (MHz)")
    parser.add_argument("--part", type=str, default="xc7vx485tffg1761-2", help="FPGA part")
    parser.add_argument("--csv", type=str, help="Output CSV file path")
    parser.add_argument("--dry-run", action="store_true", help="Generate TCL only, no synthesis")
    args = parser.parse_args()

    selected = args.bench if args.bench else list(BENCHMARKS.keys())
    results = []

    for name in selected:
        if name not in BENCHMARKS:
            print(f"Unknown benchmark: {name}")
            continue

        src, top = BENCHMARKS[name]
        src_path = KERNELS_DIR / src

        with tempfile.TemporaryDirectory(prefix=f"hls_{name}_") as tmpdir:
            work_dir = Path(tmpdir)

            if args.dry_run:
                tcl = generate_hls_tcl(top, str(src_path), args.clock, args.part, str(work_dir))
                tcl_out = f"run_hls_{name}.tcl"
                Path(tcl_out).write_text(tcl)
                print(f"Wrote {tcl_out} (dry run)")
                continue

            res = run_hls(top, str(src_path), args.clock, args.part, work_dir)
            if res:
                res["benchmark"] = name
                results.append(res)
                print(f"  {name}: LUT={res['LUT']}, DSP={res['DSP']}, lat={res['Latency_cycles']}")
            else:
                print(f"  {name}: FAILED (no synthesis report found)")

    if args.csv and results:
        _write_csv(args.csv, results)
        print(f"Results written to {args.csv}")


def _write_csv(csv_path, results):
    fields = ["benchmark", "LUT", "FF", "DSP", "Latency_cycles", "Clock_MHz"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r)


if __name__ == "__main__":
    main()

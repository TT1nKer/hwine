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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", choices=["fir", "gemm", "dct"], default="fir")
    parser.add_argument("--taps", type=int, default=8)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    out_dir = "benchmarks/hls_baseline"
    os.makedirs(out_dir, exist_ok=True)

    kernels = ["fir", "gemm", "dct"] if args.all else [args.kernel]
    for kernel in kernels:
        taps = args.taps
        source = generate_hls(kernel, taps)
        src_file = os.path.join(out_dir, f"{kernel}_hls.cpp")
        with open(src_file, "w") as f:
            f.write(source)
        print(f"Generated: {src_file}")

if __name__ == "__main__":
    main()

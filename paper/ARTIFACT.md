# hwine Artifact — Reproduction Guide

## Prerequisites

| Dependency | Version | Required For |
|-----------|---------|-------------|
| Rust | 1.70+ | core engine, all benchmarks |
| Yosys | 0.40+ (optional) | formal equivalence verification |
| Icarus Verilog | 13.0+ (optional) | RTL syntax checking |
| Vivado 2026.1 | (optional) | synthesis / HLS baseline |
| Typst | 0.12+ (optional) | paper compilation |

## Quick Start — Core Benchmarks (no external tools)

```bash
# Rust toolchain (pinned)
cd hwine-rs
cargo test --all-targets
cargo run --release --example bench_real
cargo run --release --example stream_fir_bench
cargo run --release --example formal_equiv  # requires yosys in PATH
```

Expected output for `bench_real`:
```
========================== DCT 8-point (CHStone jpeg) ==========================
E-graph: 444cls 0.xxxs
CSD-decomposed                  6.10ns    7.5LUT     4.0DSP      164MHz
Shared-aware                    5.20ns    6.5LUT     4.0DSP      192MHz

=========================== ALL BENCHMARKS COMPLETE ============================
```

Expected output for `stream_fir_bench`:
```
  PARETO FRONTIER 
    #   Delay(ns)      LUT       FF      DSP     Cycles   Op
    1       ...        ...      ...      ...       ...     ...
```

## Paper Claim → Artifact Mapping

| Paper Claim | Script / Command | Expected Evidence |
|------------|-----------------|-------------------|
| DCT 8-point: 8 DSP → 78 LUT | `cargo run --release --example bench_real` | CSD-decomposed row: DSP=0 |
| GEMM N=32: 31→5 levels | `cargo run --release --example bench_real` | Serial depth 31→Tree depth 5 |
| FIR matches Kastner Fmax 308 MHz | `cargo run --release --example gen_all_kastner_fir` + Vivado | synth report: Fmax ≥ 300 MHz |
| DSP pre-adder: 1 DSP48E1 + 0 arithmetic LUTs | Vivado: `synth_dsp_preadd.tcl` | Utilization: 1 DSP, LUT_arith=0 |
| Streaming FIR: Pareto frontier | `cargo run --release --example stream_fir_bench` | 3+ non-dominated alternatives with cycles |
| Formal equiv: DOT8/FFT Yosys | `cargo run --release --example formal_equiv` | "✓ EQUIVALENT" for DOT8 and FFT |
| Formal equiv: DCT8 e-graph union | `cargo run --release --example formal_equiv` | "✓ PROVED" with class increase |
| Cost model: DSP exact, LUT ~20× scaling | `cargo run --release --example cost_validate` | DSP 4/4 match, LUT MAPE printed |

## Formal Equivalence (requires Yosys)

```bash
export YOSYS_PATH=/opt/homebrew/bin/yosys  # or your yosys path
cargo run --release --example formal_equiv
```

Expected output:
```
--- DCT8: CSD constant decomposition [Tier 1: e-graph union] ---
  E-graph union: ✓ PROVED | Classes: 31 → 444
--- DOT8: Associativity tree balancing [Tier 2: Yosys equiv_simple] ---
  Yosys: ✓ EQUIVALENT
--- FFT Butterfly: Gauss form [Tier 2: Yosys equiv_simple] ---
  Yosys: ✓ EQUIVALENT
=========================== VERDICT ============================
  ALL ✓ — hwine optimizations formally equivalent
```

## Vivado HLS Baseline (requires Vivado HLS)

```bash
cd benchmarks/hls_baseline
python3 run_hls.py --all --csv ../../paper/data/hls_baseline.csv
```

If Vivado HLS is unavailable, pre-computed sample data is checked in at:
`paper/data/hls_baseline_sample.csv`

## Vivado Synthesis (requires Vivado + parents-pc)

Transfer RTL to Vivado machine and run:
```bash
vivado -mode batch -source synth_benchmarks.tcl
vivado -mode batch -source synth_dsp_preadd.tcl
```

## Rust Toolchain

See `hwine-rs/rust-toolchain.toml` for pinned version.
Repo compiles with stable Rust 1.70+.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `YOSYS_PATH` | `/opt/homebrew/bin/yosys` | Yosys binary for formal verification |

## Known Artifact Limitations

- Vivado synthesis requires Windows + Xilinx license (not automated in CI)
- Vivado HLS baseline requires Vivado HLS installation
- Several IR atom operations are passthrough stubs (Slice, Extract, Quant, Dequant, Sat, Round, Route, Broadcast) — see paper §RTL Generation
- DCT8 RTL-level SAT proof exceeds Yosys timeout; uses e-graph algebraic proof

# hwine

**hardware is not enough** — and neither is hwine.

A declarative, training-free FPGA hardware optimization engine using e-graph equality saturation. **10 algebraic rewrite rules** discover optimal datapath structures competitive with expert hand-optimized designs. Verified via Vivado 2026.1 synthesis and Yosys formal equivalence.

## Key Results

On the UCSD Kastner FIR benchmark suite (Xilinx 7-series, Vivado 2026.1):

- **Identical Fmax (308 MHz)** at all 10 sizes, **fewer LUTs on 6/10**
- **DCT 8-point**: 8 DSP → 78 LUT shift-add trees via CSD decomposition
- **GEMM (N=32)**: 31 adder levels → 5 (6.2×) via associativity
- **DSP Pre-adder**: `(a+b)*c` → 1 DSP48E1 slice (verified)
- **Streaming FIR**: Pareto-optimal pipeline retiming (0.30ns–4.50ns)
- **17 unit tests**, zero clippy warnings, CI on every push

## Quick Start

```bash
git clone https://github.com/TT1nKer/hwine.git
cd hwine/hwine-rs

# Run all tests
cargo test

# Run real kernel benchmarks (DCT, FFT, GEMM, Stencil)
cargo run --release --example bench_real

# Run streaming FIR with pipeline retiming
cargo run --release --example stream_fir_bench

# Run formal equivalence verification (requires Yosys)
cargo run --release --example formal_equiv

# Build all examples
cargo build --examples --release
```

## Project Structure

```
hwine/
├── hwine-rs/          # Rust e-graph engine (core)
│   ├── src/
│   │   ├── egraph.rs  # E-graph saturation + 10 rewrite rules
│   │   ├── rtl.rs     # SystemVerilog RTL generator
│   │   ├── ir.rs      # 34 atom operations
│   │   └── cost.rs    # FPGA-aware delay cost model
│   └── examples/      # FIR generation, adder trees, benchmarks
├── benchmarks/        # UCSD Kastner FIR reference designs
├── paper/             # Paper source (typst) + compiled PDF
├── tools/             # Python analysis scripts
├── vivado_pack/       # Vivado TCL synthesis scripts
└── yosys-plugin/      # Yosys RTLIL integration
```

## How It Works

1. **E-graph saturation** — 10 algebraic rewrite rules (associativity, CSD decomposition, MAC fuse/decompose, DSP pre-adder, pipeline retiming, distributivity, identities) explore equivalent micro-architectures
2. **Multi-objective FPGA-aware extraction** — Delay/LUT/DSP/FF cost model with pipeline barrier semantics selects optimal implementation
3. **Automated pipeline retiming** — StreamFifo options created at every operation; extraction chooses Pareto-optimal pipeline depth
4. **RTL generation** — Synthesizable SystemVerilog targeting Xilinx 7-series; supports 22+ atom operations
5. **Formal equivalence** — Yosys equiv_induct for associativity/MAC patterns; e-graph union for CSD decomposition

## Citation

```bibtex
@misc{yang2026hwine,
  title = {Minimal Equality Saturation for FPGA Datapath Optimization},
  author = {Yang, Zhenghao},
  year = {2026},
  note = {arXiv preprint},
  url = {https://github.com/TT1nKer/hwine}
}
```

## Known Limitations

- **RTL generation**: Some atom operations (Slice, Extract, Quant, Dequant, Sat, Round, Route, Broadcast) are emitted as passthrough stubs rather than semantically correct hardware. Division, exponentiation, softmax, delay/buffer/scan are not supported.
- **Formal equivalence**: DCT8/Stencil2D/streaming FIR are proven at the e-graph algebraic level (same equivalence class). Full RTL-level SAT proofs via Yosys currently time out for deeply restructured designs (444 e-classes).
- **Cost model**: LUT predictions use abstract units (~20× scaling factor vs Vivado LUT6 counts). DSP predictions are exact (1:1 with DSP48E1 slices).
- **HLS baseline**: Vivado HLS baseline comparison is automated via `benchmarks/hls_baseline/run_hls.py` but requires Vivado HLS installation at runtime.

## License

MIT

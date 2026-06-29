# hwine

**hardware is not enough** — and neither is hwine.

A declarative, training-free FPGA hardware optimization engine using e-graph equality saturation. One associativity rewrite rule discovers optimal datapath structures competitive with expert hand-optimized designs.

## Key Results

On the UCSD Kastner FIR benchmark suite (Xilinx 7-series, Vivado 2026.1):

- **Identical Fmax (308 MHz)** to Kastner's hand-optimized designs at all 10 sizes
- **Fewer LUTs on 6/10 sizes** — e.g., 0.64× at 41-tap (1299 vs. 2041), 0.70× at 152-tap
- **Constant 226 MHz Fmax** for pure adder trees from 20–152 taps (2.6× over serial)
- **10 ms saturation** for 512-input trees
- **Zero errors, zero critical warnings** across all designs

Compared to existing approaches:
- **1 rule** vs. ROVER's 187 hand-written rules
- **Zero training** vs. PrefixRL's 32,000 GPU-hours
- **Open source** (Rust + SystemVerilog)

## Quick Start

```bash
# Build the Rust engine
cd hwine-rs
cargo build --release

# Generate hwine FIR designs
cargo run --example gen_all_hwine_fir

# Run on a simple adder tree
cargo run --example adder_tree -- 64
```

## Project Structure

```
hwine/
├── hwine-rs/          # Rust e-graph engine (core)
│   ├── src/
│   │   ├── egraph.rs  # E-graph saturation + 8 rewrite rules
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

1. **E-graph saturation** — A single associativity rule (`Add(Add(a,b), c) ⇔ Add(a, Add(b,c))`) explores all equivalent tree topologies
2. **FPGA-aware extraction** — Delay-weighted cost model selects the optimal structure
3. **Automated pipelining** — Per-operation register insertion at configurable granularity
4. **RTL generation** — Synthesizable SystemVerilog targeting Xilinx 7-series

The cost model is calibrated against Vivado synthesis results but requires no ML training — it encodes FPGA-relative operation costs (Add/Sub: 0.8, Shl/Shr: 0.5, Mul/Mac: 2.5, Pipe: 0.3) to correctly rank design alternatives.

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

## License

MIT

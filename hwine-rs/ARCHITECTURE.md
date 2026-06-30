# hwine-rs Architecture

## Crate Structure

```
hwine-rs/
├── src/
│   ├── lib.rs        # Public API exports
│   ├── main.rs       # CLI binary (bench, rtl, synth, softmax, interactive)
│   ├── egraph.rs     # E-graph engine (add, union, extract, saturation)
│   ├── ir.rs         # IR atom operations (AtomOp, ENode, DataType)
│   ├── cost.rs       # FPGA-aware cost model (FpgaStats, ExtractMode)
│   ├── rtl.rs        # SystemVerilog RTL generator
│   ├── error.rs      # Error types (HwineError, HwineResult)
│   ├── rewrite.rs    # Rewrite rule definitions
│   ├── tcl.rs        # Vivado TCL script generation
│   ├── capi.rs       # C FFI bindings
│   ├── builders.rs   # Shared graph construction utilities
│   ├── util.rs       # Utility functions
│   └── tests.rs      # Unit tests
└── examples/         # Benchmark and demo examples
```

## Core Pipeline

```
IR (ENode tree) → EGraph saturation → DP extraction → RTL generation
```

1. **IR Construction**: Build an e-node tree using `ENode::new(op, children, dtype)` and add nodes via `egraph.add()`.
2. **Saturation**: Apply rewrite rules iteratively via `saturate()` until no new equivalences are found.
3. **Extraction**: Select the optimal node from each equivalence class using DP with cost model (`extract_optimal`, `extract_pareto`).
4. **RTL Generation**: Walk the extracted tree and emit SystemVerilog (`generate_rtl`, `generate_pipelined_rtl`).

## E-Graph Invariants

- **Union-find**: Each e-class has a canonical parent via `parents[]` array. `canon()` finds the root.
- **Hashcons**: `hashcons: HashMap<ENode, u32>` ensures each unique e-node expression exists in exactly one e-class.
- **Canonicalization**: Before add/union, child CIDs are canonicalized via `canon_mut()`.
- **Parent tracking**: `parents_of[cid]` tracks all parent e-classes containing nodes that reference this e-class as a child. Used for congruence closure repair after union.
- **Class deletion**: Deleted classes are `None` (via `.take()`). Must be validated before access.
- **Changed tracking**: `changed` vector tracks recently modified e-classes for worklist-driven rule matching.
- **Cycle detection**: DP extraction returns infinite cost for cycles to prevent invalid zero-substitution.

## Cost Model Semantics

`FpgaStats` is a multi-objective resource vector (LUT, DSP, FF, delay_ns, cycles, Fmax_mhz).

- **Pipeline barrier**: `Pipe | StreamFifo | AccInit` resets accumulated child delay to 0 (register clk-to-q).
- **Infinite cost for cycles**: Cycle detection in DP returns `FpgaStats::infinite()` to prevent extraction of invalid structures.
- **Width-aware scaling**: LUT cost scales with bit width; DSP cost uses ceil(width/25) slices.
- **Domination**: `a.dominates(b)` iff a is ≤ b in all dimensions and < b in at least one. Includes `cycles` for pipeline-aware Pareto.

## Rewrite Rules (10 rules)

| Rule | Pattern | Gate |
|------|---------|------|
| Associativity | `Op(a, Op(b, c))` ↔ `Op(Op(a, b), c)` | Always-on |
| MAC fuse | `Add(Mul(w,a), b)` → `Mac(w,a,b)` | Always-on |
| MAC decompose | `Mac(w,a,b)` → `Add(Mul(w,a), b)` | Always-on |
| CSD constant decompose | `Mul(const, x)` → shift-add tree | Always-on |
| Distributivity | `(a+b)*c` ↔ `a*c + b*c` | Always-on |
| DSP pre-adder | `DspMul(DspPreAdd(a,b), c)` → `Mul(Add(a,b), c)` | Always-on |
| Pipeline retiming | `Op(a,b)` → `StreamFifo(Op(a,b))` | Gated |
| Add identity | `Add(x, 0)` → `x` | Always-on |
| Mul identity | `Mul(x, 1)` → `x` | Always-on |
| Sub identity | `Sub(x, 0)` → `x` | Always-on |

**Gating rationale**: Pipeline retiming is gated because infinite nesting of StreamFifo nodes would cause e-graph explosion. Always-on rules are safe (bounded growth).

## RTL Backend Contract

- **Supported ops**: Add, Sub, Mul, Mac, Shl, Shr, DspMul, DspMac, DspPreAdd, Madd, ReduceAdd, ReduceMin, ReduceMax, AccInit, AccStep, AccRead, AccReset, Pipe, StreamFifo, StreamRead, StreamWrite, Concat, Const, Var, Zero, One.
- **Passthrough stubs**: Pack, Unpack, Slice, Extract, Quant, Dequant, DequantW, Sat, Round, Route, Broadcast (emitted as wire-through).
- **Unsupported ops**: Div, Exp, Softmax, StrLit, Scan, Delay, Buffer (return `HwineError::UnsupportedRtlOp`).
- **Port deduplication**: Reused Var nodes share input ports via `port_map` dedup with conflict detection.
- **Clock inference**: `has_clk` is set automatically when sequential ops (Pipe, StreamFifo) are present.

## Extraction Modes

| Mode | Cost Function | Use Case |
|------|--------------|----------|
| `MinDelay` | `delay_ns` | Minimize critical path |
| `MinLut{max_delay}` | LUT + delay tiebreaker | Area under timing constraint |
| `MinDsp{max_delay}` | DSP + delay tiebreaker | DSP-aware optimization |
| `MinFf{max_delay}` | FF + delay tiebreaker | Register minimization |
| `Weighted{w_*}` | Linear combination | Custom tradeoffs |
| `Pareto` | Non-dominated frontier | Design space exploration |

## How to Add a Benchmark

1. Build an IR tree with `ENode::new()` and `eg.add()`.
2. Call `saturate(&mut eg, &SaturateConfig)` to explore equivalences.
3. Extract the optimal node: `eg.extract_optimal(cid, ExtractMode::MinDelay)`.
4. Generate RTL: `generate_rtl(&eg, cid, "module_name", data_width)`.
5. For synthesis: write TCL with `tcl::generate_synth_tcl()` and run Vivado.

## How to Add a Rewrite Rule

1. Add a function in `egraph.rs` following the pattern: find nodes matching a pattern, construct equivalent nodes, union them.
2. Register the rule in `saturate()` with appropriate gating (always-on or configurable).
3. Add tests verifying the rule produces expected equivalences.
4. Update `ARCHITECTURE.md` rule table.

## Error Handling

`HwineError` enum covers:
- `InvalidClass(u32)` — e-class ID out of bounds
- `DeletedClass(u32)` — referring to a merged/deleted e-class
- `CycleDetected(u32)` — circular dependency in RTL generation
- `UnsupportedRtlOp(AtomOp)` — unsupported operation in RTL
- `PortConflict{name, ...}` — RTL port direction/width conflict
- `InvalidInput(&str)` — general input validation failure
- `ExtractionFailed(String)` — extraction/RTL generation failure

All public APIs return `HwineResult<T>`. Internal helpers use `.expect()` for invariant violations (should never happen).

## Testing

- 25 unit tests in `src/tests.rs` covering associativity, CSD, MAC, DSP mapping, pipeline retiming, RTL generation, formal equivalence, and error paths.
- Doctests on key public functions (`add`, `extract_optimal`, `dominates`, `generate_rtl`).
- Examples serve as integration tests for real benchmarks (DCT, FFT, FIR, GEMM, Stencil).

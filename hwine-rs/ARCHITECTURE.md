# hwine Architecture

## Crate Overview

```
hwine-rs/
├── src/
│   ├── ir.rs        # AtomOp enum + ENode struct + DataType (37 operations)
│   ├── egraph.rs    # E-graph engine (union-find, hashcons, 10 rewrite rules, extraction)
│   ├── cost.rs      # FpgaStats + ExtractMode (multi-objective cost model)
│   ├── rtl.rs       # SystemVerilog RTL generator (RtlGen)
│   ├── capi.rs      # C FFI for Yosys/CIRCT integration
│   ├── error.rs     # HwineError enum + HwineResult type alias
│   ├── util.rs      # Shared utilities (extracted_tree_depth)
│   ├── builders.rs  # Graph construction helpers (build_vars, build_add_chain, etc.)
│   └── tcl.rs       # Vivado TCL auto-generation
```

## Core Pipeline

```
IR construction → e-graph saturation → extraction → RTL generation
     (ENode)        (EGraph::saturate)  (extract_optimal)  (RtlGen::generate)
```

## E-Graph Invariants

1. **Union-find canonicalization**: `canon(id)` follows parent chain to representative. All public methods canonicalize inputs.
2. **Hashcons**: `FxHashMap<ENode, u32>` ensures identical expressions share e-classes. `add()` canonicalizes children first, then hash-cons checks.
3. **Parent tracking**: `parents_of[child].insert(parent)` maintained on every `add()`. Used by `repair_parents()` after union.
4. **Deleted classes**: `classes[id] = None` after union merge. `_extract_dp` returns `FpgaStats::infinite()` for deleted classes.
5. **Changed list**: `self.changed` collects merged e-class IDs for next saturation iteration.

## Cost Model Semantics

- **FpgaStats::for_node**: computes `lut/dsp/ff/delay_ns/cycles/fmax_mhz` from operation type + children stats
- **Pipeline barrier**: `Pipe | StreamFifo | AccInit` reset child delay to 0 (register captures upstream path)
- **Infinite cost**: `FpgaStats::infinite()` returned for cycles/deleted classes; nodes with infinite children skipped in DP
- **dominates**: compares lut, dsp, ff, delay_ns, AND cycles (pipeline-aware Pareto frontier)
- **scalar_cost**: maps ExtractMode to single f64 for DP ranking; returns INFINITY on constraint violation

## Rewrite Rules (10 total)

| Rule | Method | Always-on? | Purpose |
|------|--------|-----------|---------|
| Associativity | `rule_assoc` | yes | Tree balancing (one-directional for performance) |
| MAC decompose | `rule_mac_decompose` | yes | Mac→Add(Mul) for optimization exposure |
| MAC fuse | `rule_mac_fuse` | yes | Add(Mul)→Mac for DSP inference |
| Add identity | `rule_add_identity` | yes | x+0→x |
| Mul identity | `rule_mul_identity` | yes | x*1→x |
| CSD decompose | `rule_const_mul_decompose` | yes | Mul(Var,Const)→shift-add tree |
| Shift simplify | `rule_shift_simplify` | yes | x<<0→x, etc. |
| Acc flatten | `rule_acc_flatten` | yes | Accumulator chain reorganization |
| Distributive | `rule_distributive` | yes | Mul(Add(a,b),c)→Add(Mul(a,c),Mul(b,c)) |
| DSP pre-adder | `rule_dsp_preadd` | yes | Mul(Add(a,b),c)→DspPreAdd(a,b,c) |

**Gated rules** (only via `saturate_retime()`):
| Rule | Method | Purpose |
|------|--------|---------|
| Pipeline retiming | `rule_pipeline_retime` | Op→StreamFifo(Op) — creates pipeline options for streaming designs |

**Why gated**: Pipeline retiming creates StreamFifo alternatives that change cycle latency. For combinational-only benchmarks, this produces Pareto-inferior results (lower delay but more FFs with +1 cycle).

## RTL Backend Contract

- **Fully supported ops**: Add, Sub, Mul, Mac, Shl, Shr, DspMul, DspMac, DspPreAdd, Pipe, StreamFifo, StreamRead, StreamWrite, Concat, ReduceAdd/Min/Max, AccInit/Step/Read/Reset, Const/Var/Zero/One
- **Passthrough stubs** (wire-through, same width): Pack, Unpack, Slice, Extract, Quant, Dequant, Sat, Round, Route, Broadcast
- **Unsupported** (panic): Div, Exp, Softmax, Delay, Buffer, Scan, StrLit
- **Port dedup**: Same Var e-class only produces one input port
- **Port conflict**: Same name with different dir/width → `HwineError::PortConflict`
- **Clock detection**: `has_clk` auto-set when Pipe/StreamFifo present; adds `clk`/`rst_n` ports

## Adding a Benchmark

1. Copy pattern from `examples/bench_real.rs`
2. Build expression with `eg.add(ENode::new(op, vec![children], dtype))`
3. Saturate with `eg.saturate(max_iter, max_classes)` or `eg.saturate_retime()` for pipelined
4. Extract with `eg.extract_optimal(root, ExtractMode::MinDelay)`
5. Generate RTL with `generate_rtl(&eg, root, module_name, width)`

## Adding a Rewrite Rule

1. Add method `fn rule_xxx(&mut self, worklist: &[u32], node_limit: usize)` in `egraph.rs`
2. Pattern: iterate worklist, clone nodes, match pattern, `self.add(new_node)`, `self.union(new_cid, original_cid)`
3. Register in `apply_rules_config()` (always-on) or `saturate_with_config_retime()` (gated)
4. Add unit test in `tests.rs`

## Public API Stability

- **Stable**: `EGraph::add`, `union`, `canon`, `extract_optimal`, `extract_pareto`, `extract_shared_aware`, `n_classes`, `union_count`, `class_nodes`; `try_add`, `try_union`, `try_extract_optimal/pareto/shared_aware`; `generate_rtl`, `try_generate_rtl`; `FpgaStats::for_node/dominates/pareto_filter/scalar_cost`
- **Experimental**: `tcl.rs`, `builders.rs`, `saturate_retime`, `extract_pareto_with_mode`
- **Internal**: `_extract_dp`, `_extract_pareto`, `_extract_depth_dp`, `compute_deduped_stats`, all `rule_*` methods

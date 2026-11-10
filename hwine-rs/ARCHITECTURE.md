# Integer RTL architecture

The supported path is:

```
wrapping integer IR → guarded algebraic rewrites → finite immutable plan
                    → optional balanced pipeline → checked SystemVerilog
```

`src/ir.rs` defines atoms and integer types. The IR also retains experimental
atoms that the RTL backend rejects. The exact supported contract is in
[RELIABILITY.md](../docs/RELIABILITY.md).

`src/egraph.rs` uses union-find and a hash-cons table to store alternative
expressions. Rewrites are restricted to compatible wrapping arithmetic; nested
patterns must retain the same width, signedness and overflow mode. The active
families are associativity, MAC fuse/decompose, add/multiply identity, CSD
constant multiplication, zero-shift elimination, distributivity and pre-add
multiply fusion. Saturating/widening arithmetic is not rewritten into modular
arithmetic. CSD construction preserves result types and uses unsigned shift
counts; its decomposition handles the entire i64 constant domain.

An explicit `EGraph::union` is a **trusted assertion by the caller**. It does not
prove equality. The backend can validate types and structure, but cannot repair
arbitrary false equalities supplied by a caller. Untrusted input must not be
allowed to assert unions. The softmax expansion and latency-changing retiming
union rule have been removed from saturation. `saturate_retime` returns an error
without changing the graph.

`src/extract.rs` produces immutable `Rc<Plan>` children with the node that was
actually costed. Bounded relaxation starts with finite leaves and accepts only
strict scalar-cost improvements. Unreachable cycles and impossible constraints
return errors, rather than a fabricated zero. It is a heuristic tree-cost search,
not an exact optimum for shared DAG area or a complete Pareto frontier. The
legacy Pareto and shallow-depth APIs are exploratory analyses, not the RTL plan.

`src/cost.rs` holds uncalibrated ranking assumptions. `output_delay_ns` records
the estimated arrival time after the latest register; `delay_ns` retains the
largest path in all stages, including paths before registers. Shared-aware
accounting deduplicates resource costs without erasing timing. A cost vector's
`cycles` alone does not establish valid operand alignment.

`src/rtl.rs` checks all reachable alternatives, extracts once, and emits those
exact child choices. It rejects unsupported operations, invalid arity/types,
wrong output width, conflicting names, and unequal operand latencies. All widths
and signedness are explicit. There are no guessed children, feedback wires or
parameter overrides that silently change semantics.

`Pipeline::EveryOp` works on a combinational plan. It registers each operation,
then adds delay registers to shorter operand branches (including constants).
The scheduler memoizes shared subplans. `Pipeline::Output` adds one output
register; `None` permits already explicitly aligned Pipe nodes. Automatic
scheduling of an already sequential plan is rejected. There is no feedback,
stalling, ready/valid handshake, FIFO or sample-history inference.

`Pipeline::EveryN(n)` generalizes EveryOp with cuts at multiples of operation
depth n and a registered final partial stage. The recursive scheduler retains
both the scheduled plan and original operation depth; it pads operands to
floor((depth-1)/n) cycles before each operation. This is a bounded structural
candidate generator, not a device-aware timing optimizer. Zero n is rejected.

```rust
use hwine_rs::{
    cost::ExtractMode,
    egraph::EGraph,
    ir::{AtomOp, DataType, ENode},
    rtl::{try_generate, Pipeline},
};

let mut graph = EGraph::new();
let a = graph.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
let b = graph.add(ENode::leaf_typed(AtomOp::Var(1), DataType::S16));
let sum = graph.add(ENode::new(AtomOp::Add, vec![a, b], DataType::S16));
graph.saturate(12, 5000);
let artifact = try_generate(
    &graph, sum, "adder", 16, ExtractMode::MinDelay, Pipeline::EveryOp,
)?;
assert_eq!(artifact.latency, 1);
// artifact.verilog is the checked hardware implementation.
// artifact.estimated contains heuristic ranking numbers, not measurements.
# Ok::<(), hwine_rs::error::HwineError>(())
```

`tools/validate.py` owns the independent mathematical and RTL specifications,
seeds, simulation scoreboard, formal commands, negative controls and measurement
collection. The fixture generator only builds IR and emits implementations; it
does not compute reference answers. All generated proof obligations and logs
are retained for inspection.

`examples/explore_fixtures.rs` declares the small experiment's template and
e-graph candidates. `tools/explore.py` pads them to a common four-cycle contract,
checks independent arithmetic and pipeline obligations, and runs ECP5 synthesis
and three placement/routing seeds. `tools/linear_check.py` normalizes only
equal-width add/subtract, constant multiply, and constant left shift modulo
2^W, consuming frontend JSON rather than the compiler IR. It rejects other
operations and partial-vector wiring. Its Python code and Yosys's frontend
are trusted; the checker is not mechanically verified. `tools/explore_report.py`
selects from proven measured candidates and exports the implementation/evidence.

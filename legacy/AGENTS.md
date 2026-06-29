# hwine — Spatial Algebra Hardware Compiler

## Project Identity

hwine = "hardware is not enough" (and hwine is not enough, self-referential).

hwine is NOT a C-to-hardware compiler. It does not infer spatial structure from
sequential programs. It only optimizes computations expressed in spatial
primitives with explicit algebraic laws.

The programmer supplies the structure. The compiler performs exhaustive
equivalence exploration. The extractor picks the best hardware implementation
under a cost model. No guessing. No intent inference.

## Architecture

hwine operates at three layers:

```
Layer 0: RISC Atom Space (tools/risc-atom/)
  Every hardware task decomposes into atomic operations.
  34 registered atoms: graph ops, scheduling ops, module ops, ILP ops.
  Each atom = 1 immutable function, refs via $-prefix, literals inline.

Layer 1: Spatial Primitives (docs/spatial-primitives.md)
  Connect compute units with FIFOs. No schedule, just topology.
  8 primitives: Map, Reduce, Pipe, Fork, Join, Stencil, Delay, Buffer.
  Each primitive → deterministic RTL template. Parameters control parallelism,
  depth, buffer sizing. Scheduling = parameter optimization, not ILP.

Layer 2: RTL Projects (projects/<name>/)
  Actual SystemVerilog implementations. Each project has rtl/, tb/, Makefile.
```

## Core Loop (Layer 2 — RTL Development)

1. **Think** — understand the spec, plan the microarchitecture
2. **Write** — write SystemVerilog RTL in `projects/<name>/rtl/`
3. **Test** — write C++ testbench, `make sim` to see waveforms
4. **Inspect** — open `.fst` with surfer, verify signals match intent
5. **Synthesize** — `make syn` to see gate-level netlist with Yosys
6. **Iterate** — fix bugs, optimize, repeat

## Core Loop (Layer 1 — Spatial Design)

1. **Decompose** — express algorithm as spatial primitives (Map, Reduce, Pipe, ...)
2. **Parameterize** — choose p, tree_depth, fifo_depth, window_size
3. **Emit** — generate RTL from primitives + parameters (deterministic template)
4. **Simulate** — `make sim` on generated RTL
5. **Optimize** — adjust parameters, re-emit, re-sim

## File Layout

```
tools/risc-atom/   RISC atom decomposer: tasks → atomic operations
docs/              AI learning reference
  sv-primer.md       SystemVerilog language reference
  tools.md           Tool usage (Verilator, Yosys, Surfer)
  spatial-primitives.md  Spatial primitives specification
lib/                Reusable components (FIFO, UART, AXI, pipe templates)
scripts/            Shared build rules (sim.mk, syn.mk)
projects/<name>/    Hardware designs
  rtl/              SystemVerilog sources (*.sv)
  tb/               Testbenches (*.cpp or *.sv)
  Makefile          Project build rules
```

## Language

SystemVerilog (`.sv`). Not plain Verilog. Use:
- `always_ff` for sequential logic (flip-flops)
- `always_comb` for combinational logic
- `assign` for simple combinational expressions
- `logic` type, not `wire`/`reg` (SystemVerilog unifies them)
- `package` for shared constants/types
- `interface` for buses (AXI, etc.)

## Simulation

Verilator preferred. It compiles SystemVerilog → C++ → native binary.

```bash
make sim    # compile + run simulation, generate .fst waveform
make wave   # open waveform in surfer
```

## Synthesis

Yosys produces gate-level netlists. Use `make syn`.

## Rules for AI

- NEVER write a module without a testbench in the same commit
- NEVER use `wire`/`reg` — always `logic`
- NEVER leave uninitialized state — use reset for all sequential logic
- ALWAYS separate combinational and sequential logic into different blocks
- ALWAYS use `always_comb` not `always @(*)` for combinational
- PREFER explicit FSM states over implicit state

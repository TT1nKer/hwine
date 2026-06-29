# Related Work

hwine sits at the intersection of spatial computation, equality saturation,
and hardware synthesis. This document maps the landscape as of June 2026.

## E-Graphs + Hardware

### ROVER (Intel, ISCA 2024)
**RTL Optimization via Verified E-Graph Rewriting**

Formulates datapath optimization as e-graph rewriting with Intel-designed mixed
precision rewrite rules. Uses ILP extraction with a custom cost model.
Generates verification certificates for industrial tools. Achieves up to 63%
area reduction on Intel benchmarks. Key contribution: shows e-graphs work for
industrial RTL datapath optimization.

### ASPEN (MLCAD 2025)
**LLM-Guided E-Graph Rewriting for RTL Datapath Optimization**

Replaces handcrafted rewrite rules and cost models with LLM-guided rewrite
generation. LLM proposes rewrites, e-graph applies them, EDA tool feedback
evaluates quality. 16.51% area and 6.65% delay improvement over manual e-graph
approaches. Key contribution: removes the need for human-designed rewrite rules
and proxy cost models.

### RTLScout (Huawei, June 2026)
**Joint Agentic Code and Synthesis Optimization**

LLM agent writes, evaluates, and refines RTL using PPA feedback from Yosys
and OpenROAD. Multi-run elite pool framework where best designs seed subsequent
runs. On FP16 multiplier: 35% area reduction, 45% delay reduction. Key
contribution: combines agentic code generation with synthesis optimization
in a closed feedback loop.

### SEER (2025)
**Super-optimization Explorer using E-graph Rewriting for HLS**

Uses e-graphs to explore HLS optimization spaces. Combines e-graph rewriting
with multi-objective optimization for HLS directive selection. Parallel
exploration of optimization strategies.

### Churchroad (2025)
**FPGA Technology Mapping via Equality Saturation**

Scales equality saturation to FPGA technology mapping. Handles DSP mapping
and reduces reliance on hand-written sketches. Key contribution: applies e-graph
methods to FPGA primitive selection.

## Accelerator Design Languages & Compilers

### Calyx (ASPLOS 2021, ongoing)
**Compiler Infrastructure for Accelerator Generators**

Separates hardware structure (components + wires) from control (FSM lowering).
Uses MLIR-based flow. Can target FPGAs via CIRCT. The most mature open-source
accelerator compiler infrastructure. Key: structural-program separation.

### Dahlia (FPGA 2021)
**Imperative Accelerator Language with Time-Sensitive Types**

Uses affine types to ensure predictable hardware realizability. Prevents
generation of unpredictable hardware from imperative code. Type system
guarantees pipeline-ability.

### Allo (PLDI 2024)
**Python-embedded MLIR-based Accelerator Design**

Decouples algorithm specification from hardware customization. Uses
schedule-language separation to enable design space exploration. Python-based
with MLIR dialect support.

### From PyTorch to Calyx (Dec 2025)
**End-to-end Open-Source Compiler for ML Accelerators**

Allo → Calyx → CIRCT → SystemVerilog pipeline. First complete open-source
toolchain from ML model to synthesizable hardware. Validates the Calyx/CIRCT
stack for ML workloads.

## Tensor Program Optimization

### Glenside (MAPS 2021)
**Pure Tensor Program Rewriting via Access Patterns**

Represents tensor programs as pure access patterns. Uses equality saturation to
map program fragments to hardware accelerator invocations. Automatically
discovers classic data layout transformations (e.g., im2col). Key: pure
functional representation enables rewriting.

### Tensat (2021)
**Equality Saturation for Tensor Graph Superoptimization**

Solves phase ordering problems in tensor graph optimization. Achieves up to 16%
speedup with 48× less optimization time. Key: e-graph resolves rewrite ordering.

### Trinity (ASPLOS 2026)
**Tile-level Equality Saturation for Tensor Programs**

First tensor optimizer achieving joint optimization at tile granularity.
IR exposes memory operations, compute, loops, and sequential structures on tiles
as first-class operations. Key: scales e-graph optimization to tensor programs.

## E-Graph Foundations

### egg (POPL 2021)
**Fast and Extensible Equality Saturation**

The foundational e-graph library in Rust. Introduced e-class analysis and
extensible rewrite rules. Basis for most subsequent e-graph work.

### Optimism in Equality Saturation (PLDI 2026)
**Optimistic E-Class Analysis**

Shows that naive optimistic analysis in e-graphs can be unsound due to
representation subtleties. Proposes a sound optimistic analysis algorithm for
SSA programs. Key: enables precise analysis in cyclic e-graphs.

## Pipeline & IR-Level Optimization

### PipeRTL (May 2026)
**Timing-Aware Pipeline Optimization at CIRCT IR Level**

Formulates register relocation as a global min-cost flow problem at IR level,
before lowering to netlist. Uses learned timing predictor. Built on CIRCT.
Key: shows IR-level pipeline optimization is viable and improves downstream QoR.

## Comparison to hwine

| System | Input | Optimization | Extraction |
|--------|-------|-------------|------------|
| ROVER | RTL datapath | e-graph + manual rules | ILP + cost model |
| ASPEN | RTL datapath | e-graph + LLM rules | EDA feedback |
| Calyx/Dahlia | Accelerator DSL | Compiler passes | FSM lowering |
| Glenside | Tensor programs | e-graph rewrites | Hardware mapping |
| Trinity | Tensor programs | Tile-level e-graph | - |
| PipeRTL | CIRCT IR | Min-cost flow | Register relocation |
| **hwine** | Spatial primitives | Algebraic + impl e-graph | Hardware cost model |

hwine's unique position: starts from spatial primitives (Map, Reduce, Pipe,
Stencil, Scan) rather than RTL, tensor graphs, or imperative code. The
algebraic laws of the primitives drive equivalence exploration. This is
complementary to existing work — hwine could lower to Calyx/CIRCT or
target ROVER-style RTL rewriting as a backend.

## Key References

- Coward et al., "ROVER: RTL Optimization via Verified E-Graph Rewriting", ISCA 2024
- Zhang et al., "ASPEN: LLM-Guided E-Graph Rewriting for RTL Datapath Optimization", MLCAD 2025
- Arnold et al., "RTLScout: Joint Agentic Code and Synthesis Optimization", June 2026
- Yin et al., "PipeRTL: Timing-Aware Pipeline Optimization at IR-Level", May 2026
- Smith et al., "Pure Tensor Program Rewriting via Access Patterns", MAPS 2021
- Yang et al., "Equality Saturation for Tensor Graph Superoptimization", 2021
- Trinity, "Tile-level Equality Saturation for Tensor Programs", ASPLOS 2026
- Nigam et al., "A Compiler Infrastructure for Accelerator Generators", ASPLOS 2021
- Nigam et al., "Dahlia: Predictable Accelerator Design", FPGA 2021
- Arbore et al., "Optimism in Equality Saturation", PLDI 2026
- Willsey et al., "egg: Fast and Extensible Equality Saturation", POPL 2021

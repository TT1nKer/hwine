# Reliable integer subset

This contract applies to `rtl::try_generate` / `try_generate_rtl` and the checked
RTL wrappers. The wider IR, exploratory CLI modes, C ABI, old Python backend,
Yosys plugin, historical paper and old benchmark examples are not a general
verified compilation system.

## Values and operations

- Width is 1–64 bits. Both unsigned and signed two's-complement values are
  supported. Every value uses `OverflowMode::Wrap`.
- Add, Sub, Mul, ReduceAdd, Mac, Madd, DspMul, DspMac and DspPreAdd operate modulo
  2^W. MAC means `a*b+c`; pre-add means `(a+b)*c`. DSP atom names express
  arithmetic patterns, not a promise to infer a particular physical DSP count.
- All arithmetic data operands and results must have exactly the same type.
  There is no implicit widening, narrowing or signedness conversion. The module
  width argument must equal the root width. Each wire uses its node's type.
- `Const(i64)` is reduced modulo 2^W, including i64::MIN/MAX. `Zero`, `One`, and
  indexed `Var` leaves are supported. One variable cannot have conflicting types.
- `ReduceMin` / `ReduceMax` are binary comparisons using the declared signedness.
- `Shl` is logical left shift. `Shr` is arithmetic for signed data and logical
  for unsigned data. The shift count is a separate unsigned 1–64-bit value.
  Counts at least W yield zero for left/logical right shifts and sign fill for
  signed right shifts; they are not reduced modulo W.
- `Pipe` is exactly one register with synchronous active-low reset, zero reset
  value, and no enable. All other sequential/stream/accumulator atoms are rejected.
- Every unlisted atom returns `UnsupportedRtlOp`; this includes Slice/Extract,
  Pack/Unpack/Concat, Sat/Round, Quant/Dequant/DequantW, Route/Broadcast,
  Div/Exp/Softmax, Scan/Delay/Buffer and StreamFifo. Sat/Wide types also fail.

Malformed nodes, invalid class IDs, mixed types within a class, invalid or
conflicting names, and impossible extraction constraints fail before returning
RTL. Fallible APIs return the specific error; convenience wrappers panic. The
`RtlGen` naming adapter accepts a complete root and emits atomically.

## Clock contract

`Pipeline::None` gives combinational RTL unless the graph contains explicit
Pipe nodes. Multi-input operations must receive equal-latency operands, including
constant operands. There is no automatic alignment in this mode.

`Pipeline::Output` adds one output register to a combinational plan.
`Pipeline::EveryOp` registers every operation and explicitly delays shorter
branches. The returned `RtlArtifact.latency` is the number L of register stages.
For inputs presented before edge n, the result is available after edge n+L−1;
L=0 is combinational. A new tuple can be presented each cycle. All registers
reset on a rising edge with `rst_n=0`. Ignore results until L non-reset edges
have filled the pipeline after startup/reset; no valid signal is generated.
The output of the two automatic pipeline modes is itself registered and zero
on reset. Explicit Pipe graphs can have combinational logic after registers.

Automatic pipelining accepts only combinational extracted plans. It is not
retiming, and does not claim to preserve the original cycle latency. The old
`saturate_retime` operation is now an error. The legacy RTL CLI now emits the
16-bit type its builders actually use, instead of silently narrowing to 8 bits. The old coarse helper now means
one output register, and the fine helper now balances branches. Callers must
use the returned latency, not the old helper's presumed behavior.

The FIR fixture consumes independent tap tuples. It is not a complete streaming
FIR with a sample-history register chain. A design mixing intentionally different
sample ages needs a richer temporal IR and is outside this release boundary.

## Validation and reproducibility

Run the commands in the root README from a clean checkout. Tool versions are
fixed by the root `rust-toolchain.toml` and `tools/with_eda.sh`. The latter uses
[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) release 2026-11-09,
SHA-256 `256b113c88b8da8b363e739dd97babe89eefbfdbb84373ccae0666ae19ac304d`.
It installs only in `~/.cache/hwine-eda`; this directory is disposable. An
explicit `HWINE_EDA_DIR` uses existing tools, whose versions enter the report.

The test layers are separate:

1. Rust regressions check rejection paths, type guards, aliases, extraction
   constraints, shared costs, full i16 CSD reconstruction plus i64 extrema, and
   timing before/after pipeline barriers. Cargo example targets are compilation
   checks; they are not counted as RTL functional proofs.
2. Python computes reference results with arbitrary-precision arithmetic and
   modulo reduction. Icarus drives the actual emitted hardware using exhaustive
   small domains, boundary Cartesian products and a fixed random seed. Sequential
   checks change all inputs continuously and reassert reset midstream.
3. Yosys compares generated hardware with independently authored expressions.
   Combinational cases use SAT. Each pipelined case has two required proofs:
   its exact combinational source against the independent expression, then its
   scheduled hardware against that source delayed by the reported latency, using
   temporal induction. Source RTL hashes and both proof logs are recorded. This
   composition avoids a monolithic 16-bit deep-FIR proof that timed out; it does
   not assume the source is correct. Proofs use two-state bit-vector semantics. Only checker valid/reset history is initialized;
   DUT registers are arbitrary. Reset is otherwise unconstrained, allowing later
   reset events. After pipeline fill, equivalence holds for every input sequence
   within each proved case, not just the simulation vectors. Reset output zero
   is also checked for automatic pipeline fixtures.
4. Deliberate arithmetic, signed-shift, latency and reset mutations must fail
   both simulation and proof. A deliberately wrong Python oracle must also fail.
   This detects several ways a checker could pass without checking useful behavior.
5. Fifteen 16-bit arithmetic/FIR implementations go through Yosys xc7 technology
   mapping. The report separates mapped cell counts from estimated cost fields.

The default suite explicitly excludes the two signed/unsigned 64-bit CSD
rewrites of multiplication by i64::MAX from its formal requirement. The initial
SAT attempt on the unsigned case timed out at 45 seconds; both cases remain
mandatory simulation checks. `--extended-formal` attempts these proofs and fails
on timeout. A new or unexpected timeout in the required proof scope is an error,
never converted into success. `--filter NAME` is a diagnostic subset and is
recorded as such; it is not the full acceptance command.

A successful run writes `build/validation/summary.json` with source/RTL hashes,
tool versions, seed, per-case coverage, proof scope and mapped cells. A failed
run removes a previous success summary but keeps commands, RTL, vectors and logs.
CI uploads the evidence even on failure. The report does not rely on a shared
e-class, a successful syntax check or successful synthesis as functional proof.

## Measurement limits

`FpgaStats` has heuristic LUT/DSP/FF and delay numbers. The model is not calibrated
for a specific device, and DSP tiling/constant propagation/inference can change
actual counts. It uses a tree objective; shared-aware accounting is an estimate
for a chosen plan, not a globally optimal shared circuit. Delay retains both
completed stage maxima and current output arrival. Setup time, placement, routing,
clock uncertainty and physical resource constraints are not modeled. Its Fmax
field is derived from these assumptions, not measured frequency.

Yosys `synth_xilinx -family xc7 -noiopad -noclkbuf` gives real results from that
mapping flow. It does not run Vivado, place-and-route, timing closure or hardware.
No Vivado or FPGA board validation is claimed for this branch. Historical
Vivado CSVs and paper conclusions have not been revalidated and cannot establish
the correctness or performance of the changed pipeline backend.

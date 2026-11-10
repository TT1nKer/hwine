# Local validation record — 2026-11-10

This is the historical first reliable-integer record. The later grouped-pipeline
regression and ECP5 placement/routing experiment are recorded separately in
[ECP5_EXPLORATION.md](ECP5_EXPLORATION.md); the results below remain tied to their
original source commit and have not been overwritten.

Source implementation: `4b626c714fcf8c8a004972d3fbc6ae75554725ff`, based on
`0fb591aefbf7aa9263e6ecb19f8fd04b89a2c40f`. Branch: `fix/reliable-integer-rtl`.
These results were reproduced from a clean detached checkout with a fresh Cargo
target directory and no generated RTL. No push, release, Vivado, remote server
or FPGA board work was performed. Documentation/evidence-only commits follow the
source implementation.

The [machine-readable record](validation-2026-11-10.json) contains source and RTL
hashes, tool versions, per-case coverage, proof status, timings and mapped cells.
All 249 RTL hashes, comparison counts, proof statuses, and all 15 synthesis cell
dictionaries matched an earlier run in the working tree. Execution durations are
not expected to be identical.

## Completed checks

| Check | Actual result |
| --- | --- |
| Rust formatting | Pass |
| Clippy library, warnings denied | Pass |
| Rust tests | 26 unit + 11 integration tests pass |
| Documentation tests | 4 pass |
| Example targets | All compile; compilation is not claimed as functional proof |
| Icarus RTL simulation | 249 implementations; **1,982,765 output comparisons** |
| RTL equivalence | **247 implementations proved**: 229 combinational + 18 sequential |
| Sequential proof composition | All 18 exact combinational source modules independently proved, then temporal induction of the scheduled implementations |
| Negative controls | Wrong Python answer, add→subtract, arithmetic→logical shift, off-by-one latency and disabled reset are all rejected; the four RTL mutations fail both simulation and proof |
| Yosys xc7 synthesis | 15 implementations; `check -assert` passes |
| Remote GitHub CI for this branch | Not run: branch remains local |

Simulation uses exhaustive domains up to 16 combined input bits, boundary
Cartesian products and 1,024 seeded random vectors for larger domains. It covers
signed/unsigned arithmetic at representative 1/4/8/16/32/64-bit widths, large
shift counts, two's-complement extremes, shared expressions, FIR3 tap tuples and
uneven addition trees. Pipelined checks drive changing inputs each cycle and
assert reset again midstream. The exact case matrix is in the JSON record;
this does not claim an exhaustive proof of the library for arbitrary graphs.

The CSD regression also reconstructs every i16 coefficient and i64::MIN/MAX in
i128 arithmetic. It does not substitute for the separate RTL proofs.

## Actual synthesis measurements

Yosys `synth_xilinx -family xc7 -noiopad -noclkbuf`, **without place-and-route**.
LUT is the sum of LUT cell instances; FF counts explicit FD* cells, not internal
DSP registers. CARRY4 and other cell types are recorded separately. These are
not Vivado measurements or timing/frequency results.

| Implementation | Latency | LUT | DSP48E1 | FF | CARRY4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fir3_s16_baseline` | 0 | 0 | 3 | 0 | 0 |
| `fir3_s16_opt_delay` | 0 | 107 | 0 | 0 | 4 |
| `fir3_s16_opt_dsp` | 0 | 107 | 0 | 0 | 4 |
| `fir3_s16_pipe_output` | 1 | 108 | 0 | 16 | 4 |
| `fir3_s16_pipe_every` | 5 | 87 | 0 | 229 | 31 |
| `chain_s16_baseline` | 0 | 79 | 0 | 0 | 4 |
| `chain_s16_opt_delay` | 0 | 79 | 0 | 0 | 4 |
| `chain_s16_opt_dsp` | 0 | 79 | 0 | 0 | 4 |
| `chain_s16_pipe_output` | 1 | 78 | 0 | 16 | 4 |
| `chain_s16_pipe_every` | 3 | 64 | 0 | 96 | 16 |
| `shared_s16_baseline` | 0 | 31 | 1 | 0 | 4 |
| `shared_s16_opt_delay` | 0 | 31 | 1 | 0 | 4 |
| `shared_s16_opt_dsp` | 0 | 31 | 1 | 0 | 4 |
| `shared_s16_pipe_output` | 1 | 31 | 1 | 16 | 4 |
| `shared_s16_pipe_every` | 4 | 49 | 1 | 96 | 12 |

The FIR3 combinational tradeoff is **3 DSP48E1 → 0 DSP48E1 at the cost of 107 LUTs
and 4 CARRY4 cells**. It is not a blanket area/speed improvement. For the five-input
addition tree, the model's estimated depth improves but mapped combinational LUT
counts remain 79. The shared-expression cases estimate three DSP uses in tree
cost, while synthesis shares the multiplication and uses one. These results
illustrate why estimates and measurements must remain separate.

The fully pipelined FIR3 has five stages, 87 LUTs, 229 explicit FFs and no DSP48E1.
No measured Fmax or throughput in MHz is available. One input tuple per cycle is
the interface contract, not a demonstrated board clock rate.

## Proof and tooling limits

- `const_max_u64_opt_dsp` and `const_max_s64_opt_dsp` have simulation evidence only.
  The initial unsigned 64-bit CSD SAT attempt timed out after 45 seconds. Both
  cases are explicitly excluded from the default formal scope and the count of
  247. `--extended-formal` attempts them and fails if they cannot be proved.
- A direct 16-bit deep-FIR temporal proof also timed out. The final flow uses two
  complete RTL proofs: exact combinational source versus independent arithmetic,
  followed by pipeline versus delayed source. Both pass; no e-class membership
  is used as proof and no failed obligation is relabeled as success.
- Formal proofs use two-state bit-vector semantics, arbitrary DUT initial state,
  checker valid/reset history initialized to zero, and arbitrary later reset
  events. Results are compared after the declared fill latency; automatic
  pipeline outputs are additionally required to be zero on reset.
- Vivado, place-and-route timing, board validation, complete sample-history FIRs,
  handshakes, arbitrary user-supplied unions and unsupported IR atoms remain
  outside this evidence. Historical paper/Vivado results were not rerun.
- The historical GitHub run
  [30323356376](https://github.com/TT1nKer/hwine/actions/runs/30323356376)
  failed at `cargo fmt --check`; Clippy and tests were skipped. Formatting is now
  fixed repository-wide. The updated local CI recipe also passes, but no remote
  green status is claimed.

## Reproduce and inspect

Use the exact commands in [README](../README.md), checking out the source commit
above or the final documentation commit. The local tool versions were:

- Rust 1.96.0 (`ac68faa20`)
- Yosys 0.70+360 (`5e740962d`)
- Icarus Verilog 14.0 development build (`s20260301-918-g3e2189b36-dirty`)
- Python 3.14.8

The EDA binaries came from the checksum-pinned OSS CAD Suite archive in
`tools/with_eda.sh`. Their development labels are recorded as returned by the
tools, not presented as stable upstream release numbers. Python uses only the
standard library. Local reproduction supplied the verified installation via
`HWINE_EDA_DIR`; automatic setup downloads that same pinned archive.

Generated RTL, reference miters, vectors, Yosys scripts and raw tool logs are
retained locally under `build/clean-validation/`, with Rust logs under
`build/clean-rust-evidence/`. A new run writes `build/validation/`. CI uploads that
directory even on failure. No proprietary tools or results are needed for the
required open-source checks.

# Project status — 2026-11-10 (Toronto)

hwine is a reproducible research prototype for generating verified, measured
FPGA arithmetic kernels. Its concrete workflow is a signed coefficient vector
and constraints → finite template/e-graph candidates → correctness checks →
ECP5 synthesis/routing → selection and an RTL/evidence export. The strongest
current result is improved coverage under hardware constraints. The incremental
value of e-graph extraction is smaller and remains a research question.

## Implemented and checked

| Component | Current boundary | Evidence |
| --- | --- | --- |
| Rust integer backend | Checked same-width wrapping arithmetic; explicit types and balanced pipelines; unsupported operations rejected | [Contract](RELIABILITY.md), [architecture](../hwine-rs/ARCHITECTURE.md) |
| Custom dot products | 2–8 independent inputs, signed widths 2–16, explicit coefficients; external latency 2–16 and II=1 | [CLI](ECP5_EXPLORATION.md#reproduce-and-export), [latency controls](../tools/check_latency.py) |
| Verification | Independent arithmetic simulation, restricted exact source normalization, SMT pipeline base/induction checks and reset/error controls | [Frozen evidence](ECP5_HOLDOUT.md) |
| Physical selection | Two synthesis modes, three routing seeds, cell/FF/DSP constraints and minimum-seed internal Fmax; exports RTL with replayable evidence | [Experiment contract](ECP5_EXPLORATION.md), [selector](../tools/explore_report.py) |
| Cluster execution | Pinned CPU-only Slurm runs and immutable experiment checkouts; one pilot reproduced local measurements | [Frontenac](FRONTENAC.md) |
| Reproducibility | Source/tool fingerprints, raw-artifact audit, cross-machine and expanded-candidate comparisons, GitHub CI | [Comparison tool](../tools/compare_candidate_extension.py), [negative controls](../tools/check_comparison.py) |

The wider integer library covers more operations and widths than the dot-product
experiment. Neither the case proofs nor the experiment establish correctness
for arbitrary compiler inputs. Resource estimates in the extractor remain
heuristics; selection uses measured synthesis/routing results.

## Established results

The initial 18-instance ECP5 experiment verified 417 distinct implementations.
Templates improved cells on 11 instances and made one more feasible at zero
DSP / 150 MHz. Its e-graph candidates added no resource benefit at those
constraints. This motivated the separate full-width-coefficient experiment.

The frozen 24-case experiment verified **551 distinct implementations**, with
1,145,347 simulated output comparisons and 2,958 distinct routes. At zero DSP
and >=150 MHz, the basic baseline covers **6/24** cases; the template and combined
sets cover **20/24**. Among the six paired-feasible cases, template cell savings
are 18.0%–41.7%. These percentages do not apply to the 14 newly feasible cases.

E-graph extraction reduces cells beyond templates on **three kernels**, by
6.0%, 3.2% and 1.0%; two of those gains cost extra FFs. It also contributes nine
resource-Pareto points across eight kernels at the primary frequency threshold.
This supports retaining it as a complementary candidate source, not a general
superiority claim. See the [complete report](ECP5_HOLDOUT.md) for all cases and
frequency/DSP-budget sensitivity.

A post-hoc balanced-digit template reduced one examined case from **289 to 255
combinational cells** (11.8%) and from 179 to 169 fabric FFs. Its worst-seed
frequency falls from 205.17 to 182.18 MHz: it still meets 150 MHz, but loses
200-MHz feasibility. The remote pilot reproduced this result. A new comparison
against the original frozen run checks all 19 common RTL implementations:
proof outcomes, resources and each seed's Fmax match; 38 netlists match after
normalizing only the explicitly named EDA source-root prefix. The extension
adds three RTL implementations. This is one diagnostic case, not a completed
24-case expanded-template evaluation. The
[comparison record](frontenac-candidate-extension-2026-11-10.json) includes hashes.

## Work in progress

At the live check on **2026-11-11 00:20 UTC**, all three new Frontenac jobs were
pending; no result from them is claimed here.

| Job | Fixed experiment | State at check | Question |
| --- | --- | --- | --- |
| 12448218 | Expanded balanced-digit templates, all 24 cases, four cycles | Waiting for resources | Does the one-case gain transfer, and which e-graph gains survive a stronger baseline? |
| 12448265 | Four 16-bit/six-input cases, six cycles | Depends on successful 12448218 | Can extra pipeline stages recover feasibility, and at what FF cost? |
| 12448266 | Same four cases, eight cycles | Depends on successful 12448265 | Is a further latency increase useful? |

Protocols were frozen before these measurements:
[balanced digits](../experiments/BALANCED_DIGITS_V1.md) and
[latency](../experiments/LATENCY_V1.md). Keep every case, timeout and regression
in the report. Extra latency is an explicit tradeoff. The scheduled follow-up
audits completed evidence, reports results, and commits verified progress to
main; queue estimates are not completion promises.

The latency implementation and preceding main snapshot passed CI:
[74991c2](https://github.com/TT1nKer/hwine/actions/runs/42928609561),
[19b16f7](https://github.com/TT1nKer/hwine/actions/runs/42928998110).
These statuses concern those commits, not future changes.

## Direction and decision gates

1. Finish the three submitted sweeps and explain each change in terms of
   candidate coverage, constraints and measured resource/timing tradeoffs.
   Keep e-graph gains separate from template and pipeline gains. If stronger
   templates remove a gain, report that outcome without redefining the baseline.
2. Use the latency results to decide whether physical-delay-aware pipeline
   cuts deserve implementation. Current cuts count operation depth, not delay.
   Simply admitting longer pipelines is not evidence for a new scheduler.
3. Extend one clearly specified application boundary: full-precision signed
   dot products, then a usable FIR interface. The present holdout's exact output
   ranges need 15–17, 23–25 and 31–33 bits for input widths 8, 12 and 16. Current
   wrapped outputs do not establish full-precision filter cost. Sign extension,
   accumulator width and overflow must receive independent specifications and
   proofs before physical comparisons. Sample history, valid/stalls and rounding
   would be subsequent explicit interfaces/semantics.
4. Before a stronger research claim, compare with a properly pipelined DSP
   baseline and a frozen independent application set. The current automatic DSP
   inference is not an optimized primitive-level reference. Evaluate calibrated
   costs on held-out cases rather than fitting to this measured corpus.

This is already useful as an inspectable engineering/research artifact. General
HLS, a complete optimal Pareto extractor, automatic retiming, full precision,
saturation and board timing remain unimplemented or unvalidated. The historical
paper and Vivado results have not been regenerated for the revised compiler;
they do not form a submission-ready current paper. Algorithmic novelty and
application-level advantage still need evidence.

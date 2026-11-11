# Project status — 2026-11-10 (Toronto)

hwine is a reproducible research prototype for generating verified, measured
FPGA arithmetic kernels. Its concrete workflow is a signed coefficient vector
and constraints → finite template/e-graph candidates → correctness checks →
ECP5 synthesis/routing → selection and an RTL/evidence export. The latest evidence
shows useful template gains but weak incremental value from the current e-graph
extractor. Further investment is conditional on demonstrated external value.

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

## Latest evidence and investment decision

The [frozen 24-case experiment](ECP5_HOLDOUT.md) proved 551 distinct RTLs.
At zero DSP / 150 MHz it increased feasibility from 6/24 direct-baseline cases
to 20/24 with templates; e-graph extraction reduced cells beyond templates on
three cases. Those historical measurements remain valid.

The [complete post-hoc balanced-digit extension](ECP5_BALANCED_DIGITS.md)
proved 612 distinct RTLs and raises template feasibility to **23/24 at the same
four-cycle latency**. It absorbs all selected e-graph improvements at 150 MHz,
for every tested DSP budget. Three e-graph resource-Pareto points remain across
two cases, and some nonzero-DSP selections at 100 MHz still improve. The report
retains all 24 cases, frequency/budget sensitivity, FF costs and audit records.

A [post-hoc portfolio diagnostic](PROJECT_REASSESSMENT.md) on the original frozen
measurements finds that one fixed CSD/pipeline configuration already covers
20/24. Two fixed configurations have a mean 5.13% cell overhead versus the full
template-plus-e-graph search on the 20 paired-feasible cases. This is exploratory
internal validation, not a fresh independent holdout or external-tool comparison.

## Submitted campaign outcomes

All three jobs are terminal (2026-11-11 UTC). Original frozen checkouts were
preserved; no job was resubmitted.

| Job | Experiment | Outcome |
| --- | --- | --- |
| 12448218 | Expanded balanced-digit templates, all 24 cases, four cycles | COMPLETED 0:0; source audit and shared-RTL comparison passed |
| 12448265 | Four 16-bit/six-input cases, six cycles | FAILED 1:0 after solver unknown; incomplete result retained |
| 12448266 | Same four cases, eight cycles | CANCELLED on failed dependency; never started |

The [outcome record](frontenac-campaign-outcome-2026-11-10.json) and
[report](ECP5_BALANCED_DIGITS.md#sixeight-cycle-outcomes) preserve the diagnosis.
No six/eight-cycle performance claim is made. The automatic follow-up stops
with this report and CI; failure is not converted into a successful experiment.

## Revised direction

The [investment reassessment](PROJECT_REASSESSMENT.md) supersedes the earlier
automatic plan to add scheduling, full precision and FIR interfaces. The project
is a useful inspectable engineering artifact, but current evidence does not
justify sustained investment in a general e-graph hardware optimizer. A strong
external comparison and a concrete application need should precede more features.
The assessment proposes a bounded value test and a narrower possible reuse of
the verification infrastructure; neither is an ongoing experiment commitment.

General HLS, a complete optimal Pareto extractor, automatic retiming, full
precision, saturation and board timing remain unimplemented or unvalidated.
The historical paper and Vivado results have not been regenerated for the
revised compiler; they do not form a submission-ready current paper.

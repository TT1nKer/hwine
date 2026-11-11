# Investment reassessment — 2026-11-10

**Recommendation: close the current experiment campaign and stop treating a
larger general-purpose e-graph optimizer as the default roadmap.** Preserve the
working artifact. A further research investment should first pass a short,
externally grounded value test. More verified code or more GitHub activity is
not evidence of a useful research contribution.

## What changes the judgment

The [balanced-digit experiment](ECP5_BALANCED_DIGITS.md) improves zero-DSP,
150-MHz coverage from 20/24 to 23/24 at four cycles. But the stronger template
baseline absorbs every previously selected e-graph gain at that frequency,
including all tested DSP budgets. Three resource-Pareto points survive across
two cases; nonzero-DSP selections at 100 MHz sometimes benefit. This is a
useful negative result about the present extractor, not a verdict on e-graphs
in general. The coefficients were already inspected: it is post-hoc evidence.

A second diagnostic asks how much of the original result needs broad search.
On the **original frozen 551-RTL measurements**, one fixed template policy
(`csd_balanced`, interval 3, automatic mapping) already covers the same 20/24
cases as the full search at zero DSP / 150 MHz. Its mean cell overhead relative
to template search is 17.83%. Adding the interval-2 version gives:

| Reference | Paired feasible cases | Mean extra cells | Median extra cells | Maximum extra cells |
| --- | --- | --- | --- | --- |
| Full template set | 20 | 4.58% | 0% | 16.92% |
| Templates + e-graph | 20 | 5.13% | 1.85% | 16.92% |

The two-policy portfolio misses no feasible case and matches combined-search
cell counts on 9/20 feasible cases. The same first two policies are selected
in all 24 leave-one-case-out folds, fitting on the other 23 cases. Selection
maximizes training feasibility, then minimizes the sum of normalized cell
costs, then FFs, with deterministic ties. This is **exploratory internal
validation on an already examined corpus**, not an independent holdout.
Missing/infeasible choices remain failures. No physical run was added.

The [reproducible diagnostic](template-portfolio-diagnostic-2026-11-10.json)
includes per-case resource tuples. Recreate it with:

```bash
python3 tools/analyze_template_portfolio.py build/ecp5-holdout-v1/summary.json \
  --out build/template-portfolio-diagnostic.json
```

This weakens the earlier interpretation of “6 → 20 feasible cases” as a reason
to invest in elaborate search: much of that result comes from supplying a good
CSD/pipeline template. A 5% mean or 17% individual cell gap could still matter
in a resource-constrained application; no such application has been demonstrated.
This diagnostic measures quality on saved layouts, not an end-to-end search-time
speedup, and does not combine FF and cell costs into a total-area claim.

## External context

Existing work already covers much of the obvious expansion path:

- [ROVER](https://arxiv.org/html/2406.12421v1) describes mixed-precision RTL
  e-graph rewriting, cost-based ILP extraction and back-end verification
  certificates. Adding those ingredients alone would not distinguish hwine.
- The [SkyEgg preprint](https://arxiv.org/html/2511.15323v1) jointly selects
  implementations and schedules them using e-graphs, with MILP and heuristic
  solutions. “Make the scheduler aware of implementations” is already a
  researched direction, though a different method could still contribute.
- [FloPoCo's operator manual](https://flopoco.org/operators_5.1.git.html)
  includes constant arithmetic, configurable-precision sums of constant products
  and FIR operators with automatic untruncated output sizing. Merely adding full precision or a FIR interface would expand
  hwine's capabilities without establishing a new advantage.

These references establish overlap, not a measured defeat: their devices,
semantics and benchmarks differ. hwine has not been compared fairly against
them. A wrapping dot product cannot be credited with an area advantage over
a wider full-precision result. Likewise, the current automatic DSP inference
is not a carefully pipelined primitive-level reference.

## What outcome is realistic

| Intended outcome | Current evidence | Investment judgment |
| --- | --- | --- |
| Inspectable engineering/research artifact | Working RTL generation, independent checks, physical measurements, cluster reproduction and candid ablations | Already attainable; preserve and document it |
| Research paper with a distinctive result | No demonstrated external advantage; current e-graph gains shrink under a stronger internal baseline | Not yet supported; more feature work is insufficient |
| Tool someone adopts for an actual design | No identified external user, integration or demonstrated time/resource saving | Too early for product investment |

The six-cycle solver failure is a bounded workflow defect, not the reason for
this strategic recommendation. Fixing it would make the experiment more robust;
it would not resolve novelty or demand. The cancelled eight-cycle run supplies
no evidence either way. Their raw evidence and diagnosis are retained.

## A bounded option, not an automatic new roadmap

If further research is desired, allocate at most **3–5 working days** to one
external-value screen before implementing a larger compiler. Choose an actual
application and its arithmetic/latency/throughput contract first. Compare a tiny
fixed template portfolio and the full search against a strong, semantically
matched implementation on a predeclared independent set. Include all failures,
FF/DSP/timing costs and total tool runtime. A possible gate is a repeatable
roughly 10% resource improvement without a timing/latency concession, or a
roughly 3x search-time reduction at comparable quality. These are proposed
engineering thresholds, not predictions or publication criteria. Failure to
find a suitable application or to clear the agreed gate should end that route.

An alternative use of the existing proof/measurement infrastructure is a
**synthesis-quality counterexample tool**: find equivalent RTL pairs with
different measured quality, reduce them to small reproducible examples, and
explain the missed transformation. Five to ten useful reproducers, or an
upstream optimization adopted because of one, would be a concrete outcome.
This is an engineering hypothesis, not a novelty claim; functional synthesis
fuzzing already has precedents such as
[Verismith](https://johnwickerson.github.io/papers/verismith_fpga20.pdf).
It should begin with one useful case, not a new platform or unbounded sweep.

No new sweep, external submission or contact was performed for this assessment.
The present decision is to publish the completed evidence and failed outcomes,
stop the follow-up, and retain the project without assuming further investment.

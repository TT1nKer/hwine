# Arbitrary-coefficient holdout v1

This protocol and its coefficient manifest are committed before running the
full physical experiment. No candidate-generation, extraction, or scheduling
changes will be fitted to its measured results.

## Question

Do the previous small-constant results transfer to independently sampled
full-width signed coefficients? Does the existing e-graph extraction contribute
resources or feasibility beyond ordinary templates on this new sample?

## Frozen sample and contract

- `holdout-v1.tsv` contains 24 instances: widths 8, 12, 16; three and six
  independent inputs; four coefficient vectors per width/input-count pair.
- `tools/make_holdout_cases.py` uses Python `random.Random` with seed
  `0x484F4C444F555432`. Each coefficient is sampled uniformly from the complete
  signed W-bit range. There is no screening for digit count, symmetry, sign,
  cost, solver behavior, or physical results. The checked-in manifest is the
  authoritative sample; one seed and four vectors per stratum do not establish
  population-level performance.
- All arithmetic still wraps modulo 2^W. This experiment does not introduce
  full-precision results, saturation, rounding, or a streaming FIR interface.
- Reuse the first experiment's templates, hybrid multiplier choices, e-graph
  saturation/extractors, and operation-depth pipeline cuts. Each has exactly
  four external cycles and II=1. No additional cuts are added for this sample.
- Reuse LFE5U-25F-6 CABGA381, automatic DSP mapping and `-nodsp`, nextpnr target
  150 MHz, and seeds 1, 2, 3. Selection uses the worst of these seed estimates;
  IO remains unconstrained. These are internal timing estimates, not board data.
- Require independent source normalization, changing-input simulation with
  reset, and SMT base plus induction for every selectable implementation.
  Use the same 45-second per-phase solver limit. Report all timeouts; exclude
  unproved candidates. Unexpected proof/tool errors abort the run.

## Report all outcomes

Primary: for each of 24 cases and DSP budgets 0, 1, 2, unrestricted, minimize
combinational cells at >=150 MHz; break ties by fabric FFs, DSPs, then worst-seed
Fmax. Report baseline/template/e-graph feasibility, resource tuples, gains and
unchanged/infeasible cases. Also check whether e-graph candidates add resource
Pareto points in (comb, FF, DSP) at >=150 MHz. Budgets on one case are correlated.

Secondary: apply the same objective at 100 and 200 MHz to the same layouts;
these are sensitivity queries, not reoptimized placements. Report results by
width and input count to expose changes hidden by one aggregate percentage.

The baseline includes balanced direct arithmetic and applicable symmetric
pre-addition. Template-only search includes it, CSD, and one-native-multiplier
hybrids. E-graph extraction uses the unchanged, uncalibrated cost model. Neither
winning against basic RTL nor a larger candidate count establishes e-graph value.

## Reproduce

```bash
python3 tools/make_holdout_cases.py --out /tmp/holdout-v1.tsv
cmp experiments/holdout-v1.tsv /tmp/holdout-v1.tsv
tools/with_eda.sh python3 tools/check_custom_cases.py --out build/custom-case-check
tools/with_eda.sh python3 tools/explore.py --cases experiments/holdout-v1.tsv \
  --out build/ecp5-holdout-v1 --jobs 4
python3 tools/explore_report.py build/ecp5-holdout-v1/summary.json \
  --out build/ecp5-holdout-v1/analysis.json
```

The generated case-file snapshot and SHA-256 are saved with the run. Original
built-in fixture generation remains byte-identical, including its manifest.

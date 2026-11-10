# Expanded signed-digit templates on all 24 cases

Run the existing `--balanced-digits` option on every case in `holdout-v1.tsv`
on Frontenac, after the one-case migration pilot passed. The manifest SHA-256
remains `ac4d16ef2e68dea2094b181f2237f84484390047f9fb93fdda20c926c96efa27`.
These coefficients and the original outcomes have already been inspected:
this is a complete post-hoc extension, not a new independent holdout.

Keep widths, coefficients, wrapping arithmetic, four-cycle latency, II=1,
device, 150-MHz routing target, seeds 1/2/3, proof policy, and extraction rules
unchanged. The only search extension is the already shipped balanced
positive/negative signed-digit multiplier template. Do not fit new templates
or scheduling choices to intermediate results from this run.

Require source checking, changing-input simulation, pipeline base/induction
proofs, and the evidence audit. Preserve failures/timeouts and report all 24
cases. Compare template-only and combined selection against the frozen run
at zero DSP / >=150 MHz, then report the other DSP budgets and 100/200-MHz
sensitivity with the existing objective and tie-breaking rules. Report both
cell reductions and FF tradeoffs, feasibility, and remaining e-graph resource
Pareto points. Correlated budgets do not count as independent cases.

Cross-check all common implementations against the frozen results, including
per-seed resource/timing measurements; investigate discrepancies before
attributing changes to candidate coverage. Report the four wide six-input
cases even if they remain infeasible. Full precision and configurable latency
remain separate work.

The bounded initial allocation is four CPUs, 8 GiB RAM, two hours, CPU-only.
Use a fixed source checkout, a fresh output directory, and the existing pinned
runtime. Inspect the recorded job before retrying; do not submit duplicates.

```bash
sbatch --account="$CPU_ACCOUNT" --partition=cpubase_6hrs \
  --cpus-per-task=4 --mem=8G --time=02:00:00 \
  --job-name=hwine-balanced24 \
  --output="$HOME/hwine/logs/balanced24-%j.out" \
  --error="$HOME/hwine/logs/balanced24-%j.err" \
  tools/slurm_explore.sbatch "$HOME/hwine/runs/balanced24-20261111-r1" \
  --cases experiments/holdout-v1.tsv --balanced-digits
```

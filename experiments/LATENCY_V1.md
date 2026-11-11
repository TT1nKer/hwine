# Latency tradeoffs for the four wide dot products

The frozen four-cycle experiment left all four 16-bit, six-input cases
infeasible at zero DSP / 150 MHz. Test whether more pipeline stages make them
feasible, and measure the combinational-cell/fabric-FF tradeoff. These cases
were selected after observing failures, so this is a diagnostic follow-up,
not an independent holdout or a general claim about arbitrary workloads.

Use the same `holdout-v1.tsv` coefficient vectors, selected by the exact four
case names `random6_0_s16` through `random6_3_s16`. The manifest SHA-256 is
`ac4d16ef2e68dea2094b181f2237f84484390047f9fb93fdda20c926c96efa27`.
The initial comparison includes external latencies **4, 6 and 8**. Latency 4
comes from the full balanced-digit run, job 12448218. Freeze this plan before
measuring either new latency; do not pick a different latency per case based
on intermediate outcomes.

For the new runs, use `--balanced-digits --latency 6` and `--latency 8`,
respectively. Keep signed wrapping arithmetic, II=1, the existing templates,
e-graph extraction, scheduling intervals, device, mapping modes, target 150 MHz,
seeds 1/2/3, and 45-second solver timeout unchanged. More latency admits
previously excluded deep cores. This changes the latency contract and the
candidate set; it is not a new e-graph rewrite or a timing-aware scheduler.

One input register plus the actual core latency must fit within the external
latency; pad shorter cores to the same external cycle count. Simulation and
formal specification both use that count. Source certificates are unchanged;
the sequential base check and induction limit are latency+2. Unproved/time-out
candidates stay in the report and are excluded from selection. Require full
evidence audits, exact source hashes and retained per-seed route reports.

Compare feasibility and minimum combinational cells at zero DSP / >=150 MHz,
reporting the entire cell/FF/DSP/worst-seed-frequency tuple for each case and
latency. Also report budgets 1/2/unlimited and 100/200-MHz selection sensitivity
on the same layouts. All four cases, including unchanged or worse outcomes,
remain visible. Separate added template coverage from remaining e-graph
resource-Pareto contributions. Never present a latency increase as a free
optimization or count correlated budgets as independent trials.

The two new runs use separate outputs and a fixed source checkout distinct
from the queued four-cycle experiment. Each requests two CPUs, 8 GiB and two
hours, CPU-only; run them sequentially after the full four-cycle job succeeds.
Inspect the existing job IDs before any retry. This protocol authorizes only
these two additional sweeps, not an open-ended latency or coefficient search.

```bash
# Inside the fixed follow-up checkout, through tools/slurm_explore.sbatch:
# Same command for 8, changing both the output and --latency value.
tools/slurm_explore.sbatch "$HOME/hwine/runs/latency6-wide-20261111-r1" \
  --cases experiments/latency-wide-v1.tsv --balanced-digits --latency 6
```

`latency-wide-v1.tsv` is the exact four-row subset of the frozen manifest;
using a separate manifest avoids a substring filter accidentally adding cases.

## Contract validation before submission

`tools/check_latency.py` accepts latency-2/16 independent leaf fixtures and
latency-6/8 generated 16-bit six-input deep cores. All four pass source checks,
changing-input simulation, and sequential base/induction proofs. A one-cycle
wrong specification fails both simulation and formal checking for every tested
latency; disabling reset fails both for the eight-cycle core. Overfull cores
are rejected. The four-cycle default generated all 1,309 expanded fixture files
byte-identically to the existing local pilot. These checks establish the
implemented cycle contract on the named examples, not physical improvements.

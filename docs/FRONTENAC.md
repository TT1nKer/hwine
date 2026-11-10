# Running hwine on Frontenac

The experiment does not require the local workstation. Candidate generation,
Icarus simulation, Yosys/Bitwuzla proofs, synthesis, and nextpnr routing are CPU
workloads. They can run in a Slurm allocation on Frontenac. A GPU allocation is
not requested by this workflow.

Use the login node for source transfer, submission, and status checks. Run
installation, compilation, and experiments in the allocation, following the
[Frontenac scheduler instructions](https://cac.queensu.ca/systems/traditional-hpc/).
Queue delay can exceed the runtime of a small local experiment.

## Submit a bounded reproduction

Keep a fixed checkout for each experiment until its jobs finish. The wrapper
uses the submission directory as the repository root, an explicit output
directory, and the allocated CPU count as experiment concurrency. It refuses
direct execution without a Slurm job ID and locks each output directory.

```bash
cd "$HOME/hwine/repo"
mkdir -p "$HOME/hwine/logs"
# Set CPU_ACCOUNT to your permitted CPU association, verified with sacctmgr.
sbatch --account="$CPU_ACCOUNT" --partition=cpubase_6hrs \
  --output="$HOME/hwine/logs/pilot-%j.out" \
  --error="$HOME/hwine/logs/pilot-%j.err" \
  tools/slurm_explore.sbatch "$HOME/hwine/runs/pilot-20261110-r1" \
  --cases experiments/holdout-v1.tsv --filter random3_0_s16 --balanced-digits
```

The defaults are two CPUs, 8 GiB memory, and one hour. The first job installs
Rust 1.96.0 and the same checksum-pinned OSS CAD Suite used locally. It loads
Frontenac's Python 3.11 module; the experiment uses only the Python standard
library. No model environment or Python package installation is needed.
Runtime files live in `$HOME/hwine/runtime` unless `HWINE_RUNTIME_DIR` is set.
Installation is serialized, and generator builds retain their source-content
isolation. Rust's distribution checksum is pinned in the wrapper, from
`https://static.rust-lang.org/dist/rust-1.96.0-x86_64-unknown-linux-gnu.tar.xz.sha256`.

On success the output contains `slurm.json` (host, job ID, source commit,
wrapper hash, Python version), the complete experiment evidence,
`evidence-audit.json`, and `analysis.json`. Source hashes and measured tool
versions are also recorded by the experiment itself. A completed Slurm job
must still have a complete experiment summary and a passing evidence audit.

```bash
squeue -a -j JOB_ID
sacct -j JOB_ID --format=JobID,State,ExitCode,Elapsed,MaxRSS
tail -40 "$HOME/hwine/logs/pilot-JOB_ID.out"
tail -40 "$HOME/hwine/logs/pilot-JOB_ID.err"
```

After completion, retrieve the run directory with rsync/scp. Compare actual
RTL, proof status, resources, and all routed seeds with the existing local
`build/ecp5-expanded-csd-example` run. Do not mix a new remote run into the
frozen holdout record. The comparison tool audits both retained evidence sets
and compares their configurations, fixture files, proof outcomes, measured
resources/timing, and netlist JSON. The only netlist normalization replaces
the explicitly supplied installation root in `attributes.src`; source line
numbers, cells, connections, parameters, and other attributes remain checked.

```bash
python3 tools/compare_explorations.py \
  build/ecp5-expanded-csd-example/summary.json \
  build/frontenac-pilot-20261110/summary.json \
  --left-eda-root "$LOCAL_OSS_CAD_SUITE" \
  --right-eda-root "$REMOTE_OSS_CAD_SUITE" \
  --out build/frontenac-pilot-check/comparison.json
```

## Verified pilot — 2026-11-10

SSH access and the user's CPU association were checked live. A fixed source
checkout at `76c7462717c45d1d77cb3b6f0ae5f83387067500` was placed under
`$HOME/hwine/repo`. The wrapper passed shell syntax checks, rejected execution
without a Slurm allocation, and passed `sbatch --test-only`.

Pilot job **12446758** was submitted for `random3_0_s16` with
`--balanced-digits`, three route seeds, and the bounds above. Its output is
`$HOME/hwine/runs/pilot-20261110-r1`. It **completed successfully** on `frnt201`
at 21:06:02 UTC, with exit code `0:0`. Queue time was 2 minutes 30 seconds;
the job ran for 14 minutes 13 seconds including first-time toolchain setup.
The experiment step itself ran for 3 minutes 17 seconds. These are observations
for this run, not predicted queue times or a controlled workstation speedup.

All **22 distinct RTL implementations, 45,518 simulation comparisons, nine
source certificates, and 22 pipeline proofs** passed, with no proof timeouts.
There were 44 synthesis mappings and 108 distinct routing runs. The remote
evidence audit passed and was independently repeated on the downloaded files.

Cross-machine comparison passed:

- Experiment configurations and all 1,309 generated fixture files match exactly.
  Generation covers the manifest; physical evaluation selects only this one case.
- Proof outcomes, synthesis cell counts, and all per-seed routed resources and
  Fmax estimates match the local expanded-template run exactly.
- All 44 raw synthesis netlist hashes differ because the Yosys installation
  directory appears in source-location attributes. After replacing only that
  directory prefix, all 44 netlist JSON objects match. Original hashes and
  evidence are retained; this is not a claim of byte-identical raw netlists.
- The same 150-MHz selection uses 255 combinational cells, 169 fabric FFs,
  zero DSPs, and a worst-seed estimate of 182.18 MHz. At 200 MHz the selection
  remains 289 cells, 179 FFs, zero DSPs, and 205.17 MHz.

See the [machine-readable result](frontenac-pilot-2026-11-10.json) for original
summary hashes, audit/comparison records, accounting, and selection tuples.
Comparison controls confirmed that cell-type, parameter, source-line, and
routed-timing changes remain detectable. The Slurm runner commit also passed
[GitHub CI](https://github.com/TT1nKer/hwine/actions/runs/42899507749).

The scheduler changed the requested `cpubase_6hrs` partition to `gpu-rgrant`.
Its recorded resource request is still CPU/memory only (no GPU GRES).
Use `squeue -a` or `scontrol show job JOB_ID`: the ordinary queue listing did
not show this pending job. The preflight's next-day start estimate is not an
actual allocation or a guarantee.
The wrapper SHA-256 for this submission is
`070f00bbcb7fe48f8a40291ae9e818a31d48d76045a30d4895f13b7d017d08d8`.

The supported split is local editing and small checks, with expensive experiment
batches on Slurm. Independent coefficient cases can be split into bounded jobs
with separate outputs and a concurrency cap. This pilot verifies one case on
one compute node; a larger expanded-template sweep has not yet been submitted.

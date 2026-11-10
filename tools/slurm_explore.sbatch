#!/usr/bin/env bash
# Submit from a fixed hwine checkout. Account/partition are supplied to sbatch.
#SBATCH --job-name=hwine-explore
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
set -euo pipefail
: "${SLURM_JOB_ID:?Submit with sbatch; do not run computation on a login node}"
: "${SLURM_SUBMIT_DIR:?}"
if [[ $# -lt 1 ]]; then
  echo 'Usage: sbatch [scheduler options] tools/slurm_explore.sbatch OUTPUT_DIR [explore options]' >&2
  exit 2
fi
out=$(realpath -m "$1")
shift
for arg in "$@"; do
  case "$arg" in --out|--out=*|--jobs|--jobs=*) echo 'Output and concurrency are managed by this wrapper.' >&2; exit 2;; esac
done
cd "$SLURM_SUBMIT_DIR"
test -f tools/explore.py
mkdir -p "$out"
exec 8>"$out/.slurm.lock"
flock -n 8 || { echo 'Another job owns this output directory.' >&2; exit 1; }

# Frontenac's Python module supplies stdlib only; no pip environment is needed.
module load python/3.11
export HWINE_RUNTIME_DIR="${HWINE_RUNTIME_DIR:-$HOME/hwine/runtime}"
export CARGO_HOME="$HWINE_RUNTIME_DIR/cargo"
export CARGO_TARGET_DIR="$HWINE_RUNTIME_DIR/target"
export CARGO_BUILD_JOBS="${SLURM_CPUS_PER_TASK:-2}"
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export XDG_CACHE_HOME="$HWINE_RUNTIME_DIR/cache"
export PATH="$HWINE_RUNTIME_DIR/rust-1.96.0/bin:$PATH"

# The same pinned Rust and EDA builds as the local experiment. Installation and
# compilation happen inside this allocation, with a lock for shared runtimes.
mkdir -p "$HWINE_RUNTIME_DIR"
(
  flock 9
  version=1.96.0
  archive="rust-$version-x86_64-unknown-linux-gnu.tar.xz"
  checksum=c295047583a56238ea06b43f849f4b877fa12bfd4c7103f8d9a74c94c9c4e108
  prefix="$HWINE_RUNTIME_DIR/rust-$version"
  if [[ ! -f "$prefix/verified-$checksum" ]]; then
    staging=$(mktemp -d "$HWINE_RUNTIME_DIR/rust-install.XXXXXX")
    trap 'rm -rf "$staging"' EXIT
    curl --fail --location --retry 3 --output "$staging/$archive" \
      "https://static.rust-lang.org/dist/$archive"
    (cd "$staging" && echo "$checksum  $archive" | sha256sum --check -)
    tar -xJf "$staging/$archive" -C "$staging"
    bash "$staging/rust-$version-x86_64-unknown-linux-gnu/install.sh" \
      --prefix="$prefix" --without=rust-docs --disable-ldconfig
    test "$(rustc --version)" = 'rustc 1.96.0 (ac68faa20 2026-05-25)'
    touch "$prefix/verified-$checksum"
  fi
  tools/with_eda.sh true
) 9>"$HWINE_RUNTIME_DIR/install.lock"

python3 - "$out" <<'PY'
import datetime, hashlib, json, os, platform, subprocess, sys
from pathlib import Path
record = {
    'job_id': os.environ['SLURM_JOB_ID'],
    'host': platform.node(),
    'cpus': int(os.environ.get('SLURM_CPUS_PER_TASK', 2)),
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'wrapper_sha256': hashlib.sha256(Path('tools/slurm_explore.sbatch').read_bytes()).hexdigest(),
    'python': sys.version,
    'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
Path(sys.argv[1], 'slurm.json').write_text(json.dumps(record, indent=2) + '\n')
PY
srun tools/with_eda.sh python3 tools/explore.py --out "$out" \
  --jobs "$CARGO_BUILD_JOBS" "$@"
tools/with_eda.sh python3 tools/audit_exploration.py "$out/summary.json" \
  --check-current-sources --out "$out/evidence-audit.json"
python3 tools/explore_report.py "$out/summary.json" --out "$out/analysis.json"
echo "COMPLETE job=$SLURM_JOB_ID output=$out"

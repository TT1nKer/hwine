#!/usr/bin/env bash
# Run a command with a pinned OSS CAD Suite. No sudo or system installation.
set -euo pipefail
version=2026-11-09
archive=oss-cad-suite-linux-x64-20261109.tgz
checksum=256b113c88b8da8b363e739dd97babe89eefbfdbb84373ccae0666ae19ac304d
cache="${XDG_CACHE_HOME:-$HOME/.cache}/hwine-eda/$version"
if [[ -z "${HWINE_EDA_DIR:-}" ]]; then
  if [[ "$(uname -sm)" != 'Linux x86_64' ]]; then
    echo 'Automatic setup supports Linux x86_64; set HWINE_EDA_DIR to an existing suite on other systems.' >&2
    exit 1
  fi
  if [[ ! -f "$cache/verified-$checksum" ]]; then
    mkdir -p "$cache"
    staging=$(mktemp -d "$cache/install.XXXXXX")
    trap 'rm -rf "$staging"' EXIT
    curl --fail --location --retry 3 --output "$staging/$archive" \
      "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/$version/$archive"
    (cd "$staging" && echo "$checksum  $archive" | sha256sum --check -)
    tar -xzf "$staging/$archive" --no-same-owner -C "$staging"
    if [[ -e "$cache/oss-cad-suite" ]]; then
      echo "Unverified installation exists: $cache/oss-cad-suite; move it aside before retrying." >&2
      exit 1
    fi
    mv "$staging/oss-cad-suite" "$cache/oss-cad-suite"
    touch "$cache/verified-$checksum"
  fi
  HWINE_EDA_DIR="$cache/oss-cad-suite"
fi
for tool in yosys iverilog vvp; do
  [[ -x "$HWINE_EDA_DIR/bin/$tool" ]] || { echo "Missing $HWINE_EDA_DIR/bin/$tool" >&2; exit 1; }
done
export PATH="$HWINE_EDA_DIR/bin:$PATH"
exec "$@"

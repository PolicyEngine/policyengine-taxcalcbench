#!/usr/bin/env bash
# Populate a task-owned cache with just the pinned TY24 fixture directory.
set -euo pipefail
cd "$(dirname "$0")/.."
cache=.cache/tax-calc-bench
revision=$(uv run --frozen python -c 'from taxcalcbench_pe.corpus import REVISION; print(REVISION)')
if [[ ! -e "$cache" ]]; then
  mkdir -p .cache
  staging=$(mktemp -d .cache/fetch.XXXXXX)
  trap 'rm -rf -- "$staging"' EXIT
  git -C "$staging" init --quiet
  git -C "$staging" remote add origin https://github.com/column-tax/tax-calc-bench.git
  git -C "$staging" sparse-checkout init --cone
  git -C "$staging" sparse-checkout set tax_calc_bench/ty24/test_data
  git -C "$staging" fetch --depth 1 --filter=blob:none origin "$revision"
  git -C "$staging" checkout --quiet --detach FETCH_HEAD
  mv "$staging" "$cache"
fi
test "$(git -C "$cache" rev-parse HEAD)" = "$revision"

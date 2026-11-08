#!/usr/bin/env bash
# bd-ib-m26pql: run ONE shard of the per-file coverage suite.
#
# CI splits the suite's test files across parallel k3s jobs, then
# check-per-file-coverage combines every shard's coverage data and runs the
# unchanged canonical per-file verifier over the combined `.coverage`. This
# script is the shard half. It only RECORDS coverage: a shard covers a
# fraction of the code, so it never judges coverage itself (fail-under 0,
# no report), and the per-file verdict stays the combine job's alone.
#
# Usage: just-coverage-shard.sh <shard-index 1..N> <shard-count N>
#
# The shard set is every tracked test file pytest would collect under
# `testpaths = ["tests"]` (pytest's default `test_*.py` / `*_test.py`
# patterns), sorted, dealt round-robin: file i goes to shard (i mod N) + 1.
# The shards are therefore disjoint and their union is the whole suite.
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^[1-9][0-9]*$ || ! "$2" =~ ^[1-9][0-9]*$ || "$1" -gt "$2" ]]; then
    echo "usage: $0 <shard-index 1..N> <shard-count N>" >&2
    exit 2
fi
shard_index=$1
shard_count=$2

mapfile -t all_files < <(
    git ls-files 'tests/**' | grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$' | LC_ALL=C sort
)
if [[ ${#all_files[@]} -eq 0 ]]; then
    echo ":: coverage-shard: no tracked test files found" >&2
    exit 1
fi

shard_files=()
for i in "${!all_files[@]}"; do
    if (( i % shard_count == shard_index - 1 )); then
        shard_files+=("${all_files[$i]}")
    fi
done

workers=$(bash dev-tooling/just-test-nprocs.sh)
echo ":: coverage-shard ${shard_index}/${shard_count}: ${#shard_files[@]} of ${#all_files[@]} test files; pytest-xdist workers=${workers}"

mkdir -p .coverage-shards
# Same pytest flags as just-check-per-file-coverage.sh, plus a shard-named
# data file and fail-under 0 (pyproject's fail_under=100 cannot hold for a
# fraction of the suite; the combined data is held to it downstream).
env COVERAGE_FILE=".coverage-shards/.coverage.shard-${shard_index}" uv run pytest \
    -n "$workers" \
    --basetemp="${TMPDIR:-/tmp}/pytest" \
    --durations=0 --durations-min=10 \
    --cov --cov-branch --cov-config=pyproject.toml --cov-report= --cov-fail-under=0 \
    "${shard_files[@]}"

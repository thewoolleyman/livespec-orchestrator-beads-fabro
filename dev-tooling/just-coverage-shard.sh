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
# patterns). bd-ib-eq5ics: the files are balanced by MEASURED duration, not
# dealt round-robin (round-robin left the slowest shard about 5 minutes behind
# the fastest on the median run, and every shard waits on its slowest sibling).
# The committed table dev-tooling/coverage-shard-durations.tsv holds one
# `<test file path><TAB><seconds>` row per test file; the longest remaining file
# goes to the shard with the smallest running total (ties: lowest index, then
# path order). A tracked file the table does not list costs the table's mean, so
# it is still assigned, and a table row whose file is gone is ignored. Every
# shard computes the same plan from the same inputs, so the shards are
# disjoint and their union is the whole suite. `just coverage-shard-durations`
# regenerates the table from one pytest run.
#
# LIVESPEC_COVERAGE_SHARD_DURATIONS overrides the table path;
# LIVESPEC_COVERAGE_SHARD_LIST_ONLY=1 prints the shard's files, one per line,
# and stops before running pytest.
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

durations_file=${LIVESPEC_COVERAGE_SHARD_DURATIONS:-$(dirname "${BASH_SOURCE[0]}")/coverage-shard-durations.tsv}
if [[ ! -r "$durations_file" ]]; then
    durations_file=/dev/null
fi
# awk #1 prices every tracked file (table value, else the table's mean, else 1);
# sort puts the longest first; awk #2 deals each file to the least-loaded shard.
mapfile -t shard_files < <(
    printf '%s\n' "${all_files[@]}" |
        awk -F '\t' -v table="$durations_file" '
            FILENAME == table {
                if ($0 ~ /^#/ || NF < 2) { next }
                seconds[$1] = $2 + 0
                total += $2
                rows += 1
                next
            }
            { files[++n] = $0 }
            END {
                fallback = (rows > 0) ? total / rows : 1
                for (i = 1; i <= n; i++) {
                    cost = (files[i] in seconds) ? seconds[files[i]] : fallback
                    printf "%.6f\t%s\n", cost, files[i]
                }
            }
        ' "$durations_file" - |
        LC_ALL=C sort -t $'\t' -k1,1nr -k2,2 |
        awk -F '\t' -v count="$shard_count" -v want="$shard_index" '
            BEGIN { for (s = 1; s <= count; s++) { load[s] = 0 } }
            {
                best = 1
                for (s = 2; s <= count; s++) { if (load[s] < load[best]) { best = s } }
                load[best] += $1
                if (best == want) { print $2 }
            }
        '
)

if [[ "${LIVESPEC_COVERAGE_SHARD_LIST_ONLY:-}" == "1" ]]; then
    printf '%s\n' "${shard_files[@]}"
    exit 0
fi

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

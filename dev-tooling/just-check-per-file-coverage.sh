#!/usr/bin/env bash
# Deliberately omit errexit so the per-file coverage verifier still runs after pytest.
set -uo pipefail

pytest_rc=0
# Clean-env producer: COVERAGE_FILE unset so the repo-root .coverage exists for
# the canonical verifier even under the dispatcher's namespaced export.
# Keep pytest fixture paths short enough for AF_UNIX sockets when the concurrent
# dispatcher gives this coverage lane an isolated TMPDIR.
# Every test phase that takes 10 s or more is listed with its wall clock, so a
# slow test's duration on the CI runner can be read from the job log rather
# than inferred from the job's overall result (bd-ib-lwiila).
#
# bd-ib-m26pql: when CI has already run the suite as parallel shards
# (dev-tooling/just-coverage-shard.sh), LIVESPEC_COVERAGE_SHARDS_DIR names the
# directory holding every shard's coverage data. Combine it into the repo-root
# .coverage instead of re-running the suite; the verifier below is unchanged.
# Unset (local `just check`, the root-uid workflow, the factory), the suite
# runs here exactly as before.
shards_dir=${LIVESPEC_COVERAGE_SHARDS_DIR:-}
if [[ -n "$shards_dir" ]]; then
    shopt -s nullglob
    shard_data=("$shards_dir"/.coverage.shard-*)
    shopt -u nullglob
    if [[ ${#shard_data[@]} -eq 0 ]]; then
        echo ":: check-per-file-coverage: LIVESPEC_COVERAGE_SHARDS_DIR=$shards_dir holds no shard data" >&2
        exit 1
    fi
    echo ":: check-per-file-coverage: combining ${#shard_data[@]} coverage shards from $shards_dir"
    rm -f .coverage
    env -u COVERAGE_FILE uv run coverage combine --rcfile=pyproject.toml "${shard_data[@]}" || pytest_rc=$?
else
    env -u COVERAGE_FILE uv run pytest \
        -n "$(bash dev-tooling/just-test-nprocs.sh)" \
        --basetemp="${TMPDIR:-/tmp}/pytest" \
        --durations=0 --durations-min=10 \
        --cov --cov-branch --cov-config=pyproject.toml --cov-report= || pytest_rc=$?
fi

# The canonical verifier performs the sole coverage-data analysis. Save its
# diagnostics and exit status so check-coverage can consume precisely this
# verdict rather than re-analysing the same suite data.
mkdir -p .coverage-gates
rm -f .coverage-gates/per-file.log .coverage-gates/per-file.status
env -u COVERAGE_FILE uv run python -m livespec_dev_tooling.checks.per_file_coverage \
    2>&1 | tee .coverage-gates/per-file.log
coverage_rc=${PIPESTATUS[0]}

final_rc=$coverage_rc
if [[ "$pytest_rc" -ne 0 ]]; then
    final_rc=$pytest_rc
fi
# The aggregate coverage gate must replay only the coverage verifier's verdict.
# A pytest failure still makes this producer fail, but it is not a coverage-gate
# failure and therefore must not turn check-coverage red.
printf '%s\n' "$coverage_rc" > .coverage-gates/per-file.status

exit "$final_rc"

#!/usr/bin/env bash
# Deliberately omit errexit so the per-file coverage verifier still runs after pytest.
set -uo pipefail

pytest_rc=0
# Clean-env producer: COVERAGE_FILE unset so the repo-root .coverage exists for
# the canonical verifier even under the dispatcher's namespaced export.
# Keep pytest fixture paths short enough for AF_UNIX sockets when the concurrent
# dispatcher gives this coverage lane an isolated TMPDIR.
env -u COVERAGE_FILE uv run pytest \
    -n "$(bash dev-tooling/just-test-nprocs.sh)" \
    --basetemp="${TMPDIR:-/tmp}/pytest" \
    --cov --cov-branch --cov-config=pyproject.toml --cov-report= || pytest_rc=$?

# The canonical verifier performs the sole coverage-data analysis.  Save its
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
printf '%s\n' "$final_rc" > .coverage-gates/per-file.status

exit "$final_rc"

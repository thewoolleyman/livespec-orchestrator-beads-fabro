#!/usr/bin/env bash
# Deliberately omit errexit so the per-file coverage verifier still runs after pytest.
set -uo pipefail

pytest_rc=0
# Clean-env producer (livespec-dev-tooling-yilyxr.8, dev-tooling PR #1462
# design): COVERAGE_FILE unset so the repo-root .coverage exists for
# check-coverage's consume-once reuse even under the dispatcher's
# namespaced export, and measures identically to a clean CI job.
# Keep pytest fixture paths short enough for AF_UNIX sockets when the concurrent
# dispatcher gives this coverage lane an isolated TMPDIR.
env -u COVERAGE_FILE uv run pytest \
    -n "$(bash dev-tooling/just-test-nprocs.sh)" \
    --basetemp="${TMPDIR:-/tmp}/pytest" \
    --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing || pytest_rc=$?
env -u COVERAGE_FILE uv run python -m livespec_dev_tooling.checks.per_file_coverage
coverage_rc=$?

if [[ "$pytest_rc" -ne 0 ]]; then
    exit "$pytest_rc"
fi
exit "$coverage_rc"

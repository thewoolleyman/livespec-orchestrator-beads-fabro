#!/usr/bin/env bash
# Deliberately omit errexit so the per-file coverage verifier still runs after pytest.
set -uo pipefail

pytest_rc=0
# Clean-env producer: COVERAGE_FILE unset so the repo-root .coverage exists
# for the shared analysis result even under the dispatcher's namespaced export.
# An empty --cov-report suppresses pytest-cov's terminal report: coverage data
# is analysed once below and both gates consume the resulting cache.
env -u COVERAGE_FILE uv run pytest -n "$(bash dev-tooling/just-test-nprocs.sh)" --cov --cov-branch --cov-config=pyproject.toml --cov-report= || pytest_rc=$?
env -u COVERAGE_FILE uv run python dev-tooling/checks/coverage_gates.py analyse
analysis_rc=$?
env -u COVERAGE_FILE uv run python dev-tooling/checks/coverage_gates.py per-file
coverage_rc=$?

if [[ "$pytest_rc" -ne 0 ]]; then
    exit "$pytest_rc"
fi
if [[ "$analysis_rc" -ne 0 ]]; then
    exit "$analysis_rc"
fi
exit "$coverage_rc"

#!/usr/bin/env bash
set -euo pipefail

if [[ -f .coverage-gates.json ]]; then
    echo ":: check-coverage: reading the result analysed by check-per-file-coverage"
elif [[ -f .coverage ]]; then
    echo ":: check-coverage: analysing standalone .coverage data"
    env -u COVERAGE_FILE uv run python dev-tooling/checks/coverage_gates.py analyse
else
    echo ":: check-coverage: no .coverage data file (CI standalone job); running the suite"
    env -u COVERAGE_FILE uv run pytest -n "$(bash dev-tooling/just-test-nprocs.sh)" --cov --cov-branch --cov-config=pyproject.toml --cov-report=
    env -u COVERAGE_FILE uv run python dev-tooling/checks/coverage_gates.py analyse
fi

status=0
env -u COVERAGE_FILE uv run python dev-tooling/checks/coverage_gates.py coverage || status=$?
# Consume the data and its derived result together so no later standalone run
# can read stale coverage evidence.
rm -f .coverage .coverage-gates.json
[ "$status" -eq 0 ] || exit "$status"

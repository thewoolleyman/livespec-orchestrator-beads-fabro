#!/usr/bin/env bash
set -euo pipefail

coverage_file="${COVERAGE_FILE:-.coverage}"

if [[ -f "$coverage_file" ]]; then
    echo ":: check-coverage: reading existing $coverage_file (produced by check-per-file-coverage); no duplicate suite run"
    status=0
    uv run coverage report --fail-under=100 || status=$?
    # Consume-once (livespec-dev-tooling-yilyxr.8): delete after the read so
    # no later standalone run can report from stale coverage data.
    rm -f "$coverage_file"
    [ "$status" -eq 0 ] || exit "$status"
else
    echo ":: check-coverage: no .coverage data file (CI standalone job); running the suite"
    uv run pytest -n "$(bash dev-tooling/just-test-nprocs.sh)" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
fi

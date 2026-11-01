#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .coverage-gates/per-file.status || ! -f .coverage-gates/per-file.log ]]; then
    echo ":: check-coverage: no canonical per-file verdict; running the suite"
    set +e
    bash dev-tooling/just-check-per-file-coverage.sh
    producer_rc=$?
    set -e
    if [[ "$producer_rc" -ne 0 && ! -f .coverage-gates/per-file.status ]]; then
        exit "$producer_rc"
    fi
else
    echo ":: check-coverage: reading the canonical per-file verdict"
    cat .coverage-gates/per-file.log >&2
fi

status=$(<.coverage-gates/per-file.status)
# Consume the coverage data and its canonical verdict together so a later
# standalone invocation cannot report from stale evidence.
rm -f .coverage .coverage-gates/per-file.log .coverage-gates/per-file.status
rmdir .coverage-gates 2>/dev/null || true

[ "$status" -eq 0 ] || exit "$status"

#!/usr/bin/env bash
# Run shell lint and the hermetic fleet-launch harness.  The harness is the
# behavioural gate: a syntax check cannot detect a dropped launch condition.
set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "usage: just-check-fleet-launch.sh [scenario297]" >&2
    exit 2
fi

# The Scenario 297 slice runs the harness cases alone, so its verdict reflects
# harness behaviour rather than time spent linting. The aggregate target still
# lints every fleet-launch script before it runs the full harness.
if [ "$#" -eq 0 ]; then
    mapfile -t shell_scripts < <(git ls-files -z 'fleet-launch/*.sh' 'fleet-launch/**/*.sh' | tr '\0' '\n')

    if [ "${#shell_scripts[@]}" -eq 0 ]; then
        echo "check-fleet-launch: no tracked shell script found under fleet-launch/" >&2
        exit 1
    fi

    if command -v shellcheck >/dev/null 2>&1; then
        shellcheck --severity=warning "${shell_scripts[@]}"
        printf 'check-fleet-launch: shellcheck clean over %d shell scripts under fleet-launch/\n' \
            "${#shell_scripts[@]}"
    else
        echo "WARNING: shellcheck not found; skipping shell lint (the hermetic harness still runs)" >&2
    fi
fi

bash fleet-launch/test/run-tests.sh "$@"

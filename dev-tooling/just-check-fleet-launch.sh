#!/usr/bin/env bash
# Run shell lint and the hermetic fleet-launch harness.  The harness is the
# behavioural gate: a syntax check cannot detect a dropped launch condition.
set -euo pipefail

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

bash fleet-launch/test/run-tests.sh

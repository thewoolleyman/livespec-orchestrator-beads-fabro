#!/usr/bin/env bash
# `check-fleet-launch` — lint and hermetically test the PROVISIONAL fleet launch
# scripts under `fleet-launch/`.
#
# The shell corpus is discovered from git so a new launcher script cannot avoid
# lint merely by not being added to a hand-maintained list. The harness is the
# behavioral gate: syntax checks cannot detect a missing board read.
set -euo pipefail

mapfile -t shell_scripts < <(git ls-files -z 'fleet-launch/*.sh' 'fleet-launch/**/*.sh' | tr '\0' '\n')

if [ "${#shell_scripts[@]}" -eq 0 ]; then
    echo "check-fleet-launch: no tracked shell script found under fleet-launch/" >&2
    exit 1
fi

if ! command -v shellcheck >/dev/null 2>&1; then
    echo "check-fleet-launch: shellcheck is required to lint ${#shell_scripts[@]} fleet-launch/ scripts" >&2
    exit 1
fi

shellcheck --severity=warning "${shell_scripts[@]}"
printf 'check-fleet-launch: shellcheck clean over %d shell scripts under fleet-launch/\n' \
    "${#shell_scripts[@]}"

bash fleet-launch/test/run-tests.sh

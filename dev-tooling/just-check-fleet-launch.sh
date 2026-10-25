#!/usr/bin/env bash
# `check-fleet-launch` — lint and hermetically test the PROVISIONAL fleet launch
# scripts under `fleet-launch/`.
#
# `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts" requires `just
# check` to run this target, that it "runs shellcheck over every shell script
# under `fleet-launch/`", that it "runs a hermetic harness", and that "A syntax
# check alone MUST NOT be treated as satisfying this obligation".
#
# TWO LEGS, AND THE SECOND IS THE HARD ONE. ShellCheck is required: a runner that
# cannot inspect every launcher script cannot claim this check passed. The HERMETIC
# HARNESS always runs too, because the defect this target exists for
# passes every syntax check there is: an edit that appended a trailing comment
# to a multi-statement line silently dropped the mi-homelab board read on
# 2026-10-24, and the launcher then read the fleet as unknown and launched
# nothing for ninety minutes. Same shape as `check-bd-guard`, whose driver this
# mirrors.
#
# THE SHELL CORPUS IS DISCOVERED, NEVER LISTED. A hand-written file list is a
# lint a new script escapes by existing, so the corpus is every tracked `.sh`
# under `fleet-launch/`, taken from git. An EMPTY corpus fails: the directory
# carries shell scripts today, so discovering none means the discovery broke,
# not that the lint passed. `--severity=warning` is this repository's own
# ratified shell floor — the one `check-shell-quality` applies, where `error`
# and `warning` are findings and `info` and `style` are not — rather than a
# floor invented here.
#
# Pure shell plus the stub-driven harness: no beads, no store, no network, no
# live factory, so it runs in any tier. Not a canonical livespec-dev-tooling
# slug, so the justfile wires it in the private block.
set -euo pipefail

mapfile -t shell_scripts < <(git ls-files -z 'fleet-launch/*.sh' 'fleet-launch/**/*.sh' | tr '\0' '\n')

if [ "${#shell_scripts[@]}" -eq 0 ]; then
    echo "check-fleet-launch: no tracked shell script found under fleet-launch/," \
        "so the lint could not have reported a finding" >&2
    exit 1
fi

if ! command -v shellcheck >/dev/null 2>&1; then
    echo 'check-fleet-launch: shellcheck is required to inspect fleet-launch/' >&2
    exit 1
fi

shellcheck --severity=warning "${shell_scripts[@]}"
printf 'check-fleet-launch: shellcheck clean over %d shell scripts under fleet-launch/\n' \
    "${#shell_scripts[@]}"

bash fleet-launch/test/run-tests.sh

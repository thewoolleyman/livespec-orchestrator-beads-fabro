#!/usr/bin/env bash
# `check-fleet-launch` — the two legs `SPECIFICATION/contracts.md` §"Provisional
# fleet launch scripts" requires `just check` to run over `fleet-launch/`: a
# ShellCheck pass over every shell script there, and the hermetic launcher
# harness.
#
# The tool's name is written `ShellCheck` in this prose wherever a line would
# otherwise begin with it: a comment opening `# shellcheck ` IS a ShellCheck
# directive, so the sentence describing the leg made the tool refuse to parse
# the file it was describing.
#
# WHY TWO LEGS AND NOT ONE. The clause states the second obligation negatively —
# "a syntax check alone MUST NOT be treated as satisfying this obligation" — and
# that is not a stylistic preference. `fleet-launch/dispatch-dual.sh` is a gate
# SEQUENCE whose every interesting defect is shellcheck-clean: a refusal that
# stops refusing, an unreadable board counted as green, a FIFO queue that starves
# everything behind its head. Shellcheck cannot see any of them, so the harness
# is the leg that actually gates a launcher change, and the shellcheck leg is
# what keeps the harness from being handed a script that cannot run.
#
# WHY BOTH LEGS RUN EVEN WHEN THE FIRST FAILS. An operator fixing this gate wants
# the whole verdict, not the first line of it — the same reason the `just check`
# aggregate omits `errexit`. A shellcheck finding and a broken gate are different
# repairs, and reporting only one of them costs a second full harness run to
# discover the other.
#
# WHY THE SEVERITY FLOOR IS `warning`. It is the floor the fleet's own
# `check-shell-quality` applies (it raises a finding for `error` and `warning`
# and passes `info` and `style`), and stating it here rather than inheriting the
# tool's own default keeps the two gates from disagreeing about the same tree:
# `dispatch-dual.sh` carries one deliberate `SC2015` at `info`, and a leg that
# failed on it would make this target contradict the gate that already passes.
#
# Usage: just-check-fleet-launch.sh
# Environment:
#   FLEET_LAUNCH_HARNESS_DIR=<dir>  the launcher directory to check
#                                   (default: this repository's fleet-launch/).
# Deliberately omit errexit so both legs report before this exits non-zero.
set -uo pipefail

DEV_TOOLING_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$DEV_TOOLING_DIR/.." && pwd)
TARGET_DIR=${FLEET_LAUNCH_HARNESS_DIR:-$REPO_ROOT/fleet-launch}
SEVERITY=warning

failed=()

if [ ! -d "$TARGET_DIR" ]; then
    printf 'check-fleet-launch: no launcher directory at %s\n' "$TARGET_DIR"
    exit 2
fi

printf '::: shellcheck (severity=%s) over every shell script under %s\n' \
    "$SEVERITY" "$TARGET_DIR"
# `find` rather than a glob: the tree carries `wrappers/`, and a `*.sh` glob
# would read the top level only — a scope hole that reports as a clean run.
scripts=()
while IFS= read -r -d '' script; do
    scripts+=("$script")
done < <(find "$TARGET_DIR" -type f -name '*.sh' -print0 | sort -z)
if [ ${#scripts[@]} -eq 0 ]; then
    # Zero scripts is never the answer for this tree, and a vacuous pass is how
    # a renamed directory would read as compliant.
    printf 'check-fleet-launch: no shell script found under %s\n' "$TARGET_DIR"
    exit 2
fi
printf '  %d script(s)\n' "${#scripts[@]}"
if ! shellcheck --severity="$SEVERITY" -- "${scripts[@]}"; then
    failed+=("shellcheck")
fi

printf '::: hermetic launcher harness\n'
if ! FLEET_LAUNCH_HARNESS_DIR="$TARGET_DIR" bash "$DEV_TOOLING_DIR/fleet-launch-harness.sh"; then
    failed+=("harness")
fi

if [ ${#failed[@]} -gt 0 ]; then
    printf '\ncheck-fleet-launch: failed leg(s): %s\n' "${failed[*]}"
    exit 1
fi
printf '\ncheck-fleet-launch: shellcheck clean and every harness case passed.\n'

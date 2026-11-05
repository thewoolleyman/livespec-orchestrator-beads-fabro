#!/usr/bin/env bash
#
# Amend the Red commit outside the implement agent turn.  Engine checkpoints
# carry Green's staged implementation, so they are folded before the amend.

set -euo pipefail

readonly CHECKPOINT_LIMIT=500
readonly CHECKPOINT_SUBJECT='^fabro\([^)]*\): '
readonly HANDOFF_NAME="livespec-implement-handoff.md"
readonly OUTPUT_NAME="livespec-commit-green-output"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REENTRY_POLICY="$SCRIPT_DIR/commit-reentry-policy.sh"
readonly REENTRY_POLICY

checkpoint_commit() {
    local ref="$1"
    local subject=""
    local message=""
    subject="$(git log -1 --format=%s "$ref" 2>/dev/null)" || return 1
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    [[ "$subject" =~ $CHECKPOINT_SUBJECT ]] && grep -q '^Fabro-Run: ' <<<"$message"
}

fold_checkpoints() {
    local depth=0
    local ref="HEAD"
    local red_message=""
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_commit "$ref"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    if (( depth == 0 )); then
        return
    fi
    red_message="$(git log -1 --format=%B "$ref" 2>/dev/null || true)"
    if grep -q '^TDD-Red-Test-File-Checksum: ' <<<"$red_message"; then
        # A seeded tree may carry checkpoints from an earlier run.  Fold that
        # complete suffix into its evidence-bearing commit: an open Red is
        # completed here, while an already-Green pair is amended without losing
        # either trailer.  Leaving those checkpoints as published commits would
        # publish implementation changes with no replay evidence.
        git reset --soft "HEAD~${depth}"
    fi
}

append_failure_details() {
    local output="$1"
    printf 'Failed targets:\n'
    awk '
        /^Failed targets \([0-9]+\):[[:space:]]*$/ { printing = 1; next }
        printing && /^[[:space:]]+-[[:space:]]+/ { print; next }
        printing { exit }
    ' "$output"
    printf 'Hook output (last 80 lines):\n```text\n'
    tail -n 80 "$output"
    printf '\n```\n'
}

append_verdict() {
    local handoff="$1"
    local status="$2"
    local output="$3"
    {
        printf '\n## commit_green\n\n'
        printf 'Exit status: %s\n' "$status"
        if (( status != 0 )); then
            append_failure_details "$output"
        fi
    } >> "$handoff"
}

main() {
    local handoff=""
    local output=""
    local status=0
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    output="$(git rev-parse --git-path "$OUTPUT_NAME")"
    fold_checkpoints
    set +e
    git commit --amend --no-edit >"$output" 2>&1
    status=$?
    set -e
    cat "$output"
    append_verdict "$handoff" "$status" "$output"
    if (( status != 0 )); then
        "$REENTRY_POLICY" green \
            "${LIVESPEC_MECHANICAL_TARGETS:-check-lint,check-format,check-keyword-only-args,check-file-lloc,check-per-file-coverage}" \
            "${LIVESPEC_MECHANICAL_REENTRIES:-2}" "$output" "$handoff" "$status"
    fi
    return "$status"
}

main "$@"

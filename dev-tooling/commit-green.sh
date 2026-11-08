#!/usr/bin/env bash
#
# Amend the Red commit outside the implement agent turn.  Engine checkpoints
# carry Green's staged implementation, so they are folded before the amend.

set -euo pipefail

readonly CHECKPOINT_LIMIT=500
readonly CHECKPOINT_SUBJECT='^fabro\([^)]*\): '
readonly HANDOFF_NAME="livespec-implement-handoff.md"
readonly OUTPUT_NAME="livespec-commit-green-output"

checkpoint_commit() {
    local ref="$1"
    local subject=""
    local message=""
    subject="$(git log -1 --format=%s "$ref" 2>/dev/null)" || return 1
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    [[ "$subject" =~ $CHECKPOINT_SUBJECT ]] && grep -q '^Fabro-Run: ' <<<"$message"
}

checkpoint_run_id() {
    local ref="$1"
    local message=""
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 0
    awk '!found && sub(/^Fabro-Run: /, "") { print; found = 1 }' <<<"$message"
}

checkpoint_for_run() {
    local ref="$1"
    local run_id="$2"
    checkpoint_commit "$ref" && [[ "$(checkpoint_run_id "$ref")" == "$run_id" ]]
}

red_commit_for_current_run() {
    local ref="$1"
    local run_id=""
    local subject=""
    local message=""
    subject="$(git log -1 --format=%s "$ref" 2>/dev/null)" || return 1
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    run_id="$(git config --local --get livespec.factoryRunId 2>/dev/null || true)"
    [[ -n "$run_id" ]] \
        && [[ "$subject" == "feat: red" ]] \
        && grep -qxF "Factory-Run-Id: $run_id" <<<"$message"
}

fold_checkpoints() {
    local depth=0
    local ref="HEAD"
    local checkpoint_run=""
    checkpoint_run="$(checkpoint_run_id "$ref")"
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_for_run "$ref" "$checkpoint_run"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    if ! red_commit_for_current_run "$ref"; then
        printf '%s\n' "current run's own Red commit was not found beneath checkpoint commits"
        return 2
    fi
    if (( depth > 0 )); then
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
    local cause="${4:-}"
    {
        printf '\n## commit_green\n\n'
        printf 'Exit status: %s\n' "$status"
        if [[ -n "$cause" ]]; then
            printf 'Cause: %s\n' "$cause"
        elif (( status != 0 )); then
            append_failure_details "$output"
        fi
    } >> "$handoff"
}

main() {
    local handoff=""
    local output=""
    local status=0
    local cause=""
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    output="$(git rev-parse --git-path "$OUTPUT_NAME")"
    set +e
    cause="$(fold_checkpoints)"
    status=$?
    set -e
    if (( status != 0 )); then
        : > "$output"
        printf '%s\n' "commit_green: $cause" >&2
        append_verdict "$handoff" "$status" "$output" "$cause"
        return "$status"
    fi
    set +e
    git commit --amend --no-edit >"$output" 2>&1
    status=$?
    set -e
    cat "$output"
    append_verdict "$handoff" "$status" "$output"
    return "$status"
}

main "$@"

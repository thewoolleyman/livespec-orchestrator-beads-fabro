#!/usr/bin/env bash
#
# Make the Red commit outside the implement agent turn. The file it reads and
# writes is git-local so Fabro's checkpoint commits cannot carry it forward.

set -euo pipefail

readonly CHECKPOINT_LIMIT=500
readonly CHECKPOINT_SUBJECT='^fabro\([^)]*\): '
readonly HANDOFF_NAME="livespec-implement-handoff.md"
readonly OUTPUT_NAME="livespec-commit-red-output"

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
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_commit "$ref"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    if (( depth > 0 )); then
        git reset --soft "HEAD~${depth}"
    fi
    printf '%s\n' "$depth"
}

latest_red_test_file() {
    awk '
        /^##[[:space:]]+red([[:space:]]|$)/ { in_red = 1; next }
        /^##[[:space:]]/ { in_red = 0 }
        in_red && /^Red test file:[[:space:]]*/ {
            value = $0
            sub(/^Red test file:[[:space:]]*/, "", value)
            sub(/^`/, "", value)
            sub(/`$/, "", value)
            latest = value
        }
        END { print latest }
    ' "$1"
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
        printf '\n## commit_red\n\n'
        printf 'Exit status: %s\n' "$status"
        if [[ -n "$cause" ]]; then
            printf 'Cause: %s\n' "$cause"
        fi
        if (( status != 0 )) && [[ -f "$output" ]]; then
            append_failure_details "$output"
        fi
    } >> "$handoff"
}

main() {
    local handoff=""
    local output=""
    local test_file=""
    local status=0
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    output="$(git rev-parse --git-path "$OUTPUT_NAME")"
    test_file="$(latest_red_test_file "$handoff" 2>/dev/null || true)"
    if [[ -z "$test_file" ]]; then
        : > "$output"
        append_verdict "$handoff" 2 "$output" "latest red section names no test file"
        printf '%s\n' "commit_red: latest red section names no test file" >&2
        return 2
    fi
    fold_checkpoints >/dev/null
    git reset
    git add -- "$test_file"
    set +e
    git commit -m "feat: red" >"$output" 2>&1
    status=$?
    set -e
    cat "$output"
    append_verdict "$handoff" "$status" "$output"
    return "$status"
}

main "$@"

#!/usr/bin/env bash
#
# Classify a refused Red/Green command commit and reserve exactly one of its
# two re-entry budgets.  State is git-local: engine checkpoint commits cannot
# accidentally transport a spent budget into another run.

set -euo pipefail

failed_targets() {
    awk '
        /^Failed targets \([0-9]+\):[[:space:]]*$/ { printing = 1; next }
        printing && /^[[:space:]]+-[[:space:]]+/ { sub(/^[[:space:]]+-[[:space:]]+/, ""); print; next }
        printing { exit }
    ' "$1" | tr '\n' ' ' | sed 's/ $//'
}

counter() {
    local path="$1"
    local value
    value="$(cat "$path" 2>/dev/null || echo 0)"
    case "$value" in
        ''|*[!0-9]*) printf '%s\n' 0 ;;
        *) printf '%s\n' "$value" ;;
    esac
}

record() {
    local node="$1"
    local targets_csv="$2"
    local budget="$3"
    local output="$4"
    local handoff="$5"
    local status="$6"
    local target=""
    local targets=""
    local allowed=" ${targets_csv//,/ } "
    local mechanical=0
    local mechanical_count=0
    local ordinary_count=0
    local mechanical_counter=""
    local ordinary_counter=""
    local authorized=""
    local cause_path=""

    [[ "$status" -ne 0 ]] || return 0
    case "$budget" in ''|*[!0-9]*) budget=0 ;; esac
    targets="$(failed_targets "$output")"
    if [[ -n "$targets" ]]; then
        mechanical=1
        for target in $targets; do
            [[ "$allowed" == *" $target "* ]] || mechanical=0
        done
    fi

    mechanical_counter="$(git rev-parse --git-path "livespec-commit-${node}-mechanical-reentries")"
    ordinary_counter="$(git rev-parse --git-path "livespec-commit-${node}-ordinary-reentries")"
    authorized="$(git rev-parse --git-path "livespec-commit-${node}-reentry-authorized")"
    cause_path="$(git rev-parse --git-path livespec-stage-cause)"
    rm -f "$authorized"
    mechanical_count="$(counter "$mechanical_counter")"
    ordinary_count="$(counter "$ordinary_counter")"

    if [[ "$mechanical" -eq 1 && "$mechanical_count" -lt "$budget" ]]; then
        mechanical_count=$((mechanical_count + 1))
        printf '%s\n' "$mechanical_count" > "$mechanical_counter"
        printf 'mechanical\n' > "$authorized"
        cat >> "$handoff" <<EOF
Refusal classification: mechanical
Failed targets: $targets
Mechanical re-entries remaining: $((budget - mechanical_count))
EOF
        return 0
    fi

    if [[ "$ordinary_count" -lt 1 ]]; then
        ordinary_count=$((ordinary_count + 1))
        printf '%s\n' "$ordinary_count" > "$ordinary_counter"
        printf 'ordinary\n' > "$authorized"
        cat >> "$handoff" <<EOF
Refusal classification: ordinary
Failed targets: $targets
Mechanical re-entries remaining: $((budget - mechanical_count))
EOF
        return 0
    fi

    if [[ "$mechanical_count" -ge "$budget" && "$ordinary_count" -ge 1 ]]; then
        printf 'stage: %s\ncause: LIVESPEC_COMMIT_REENTRY_BUDGETS_EXHAUSTED: %s commit hook refused again; mechanical re-entries exhausted (%s of %s) and ordinary re-entry exhausted (1 of 1); failed targets: %s\n' \
            "$node" "$node" "$mechanical_count" "$budget" "${targets:-(none named)}" > "$cause_path"
    else
        printf 'stage: %s\ncause: LIVESPEC_COMMIT_ORDINARY_REENTRY_EXHAUSTED: %s commit hook refusal cannot use a mechanical re-entry and its ordinary re-entry is exhausted; failed targets: %s\n' \
            "$node" "$node" "${targets:-(none named)}" > "$cause_path"
    fi
}

record "$@"

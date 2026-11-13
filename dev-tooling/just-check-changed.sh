#!/usr/bin/env bash
set -euo pipefail

mapfile -t changed < <(just changed-files)
workflow=.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro
workflow_changed=$(
    {
        git diff --name-only origin/master...HEAD
        git diff --cached --name-only --diff-filter=AM
    } | grep -Fx "$workflow" || true
)

if [[ "${#changed[@]}" -gt 0 ]]; then
    echo ":: check-changed: scoping the test subset + per-file coverage gate to ${#changed[@]} changed .py:"
    printf '   %s\n' "${changed[@]}"
    echo ":: INNER-LOOP ONLY - 'just check' runs the FULL suite/AST scans at pre-push + CI"
    just check-check-coverage-incremental --paths "${changed[@]}"
fi

if [[ -n "$workflow_changed" ]]; then
    mapfile -t workflow_tests < <(rg --files-with-matches --glob '*.py' 'workflow\.fabro' tests)
    if [[ "${#workflow_tests[@]}" -eq 0 ]]; then
        echo ":: check-changed: $workflow changed but no graph-reading test could be selected" >&2
        exit 75
    fi
    echo ":: check-changed: $workflow changed; running ${#workflow_tests[@]} graph-reading tests"
    just check-staged-tests "${workflow_tests[@]}"
fi

if [[ "${#changed[@]}" -eq 0 ]] && [[ -z "$workflow_changed" ]]; then
    echo ":: check-changed: no affected source module or workflow graph could be selected" >&2
    exit 75
fi

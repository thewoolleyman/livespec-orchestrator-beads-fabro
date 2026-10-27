#!/usr/bin/env bash
set -euo pipefail

# `changed-files` intentionally returns only Python paths, which is correct for
# its incremental coverage caller but insufficient to decide whether the caller
# MAY scope a commit. A shared configuration edit can alter every test's runtime
# or the hook graph itself; treating its empty Python projection as a clean
# no-op would therefore skip the only aggregate before publication. Classify
# every changed path first and fall back before asking the Python-only helper.
mapfile -t all_changed < <(
    {
        git diff --name-only origin/master...HEAD 2>/dev/null || true
        git diff --cached --name-only --diff-filter=ADM
    } | sort -u
)

unscoped=()
for path in "${all_changed[@]}"; do
    if [[ "$path" != *.py ]]; then
        unscoped+=("$path")
    fi
done
if [[ "${#unscoped[@]}" -gt 0 ]]; then
    echo ":: check-changed: ${#unscoped[@]} changed path(s) cannot be scoped to Python tests:"
    printf '   %s\n' "${unscoped[@]}"
    echo ":: check-changed: falling back to the authoritative full aggregate"
    just check
    exit $?
fi

# A Red commit intentionally stages one failing test and no implementation.
# The Red-Green verifier still observes that failure in the enclosing hook, so
# the affected-tests gate must not execute it early and refuse the ritual.
staged=$(git diff --cached --name-only --diff-filter=AM)
test_staged=$(grep -E '^tests/.*\.py$' <<<"$staged" || true)
impl_staged=$(grep -E '^(\.claude-plugin/scripts/|dev-tooling/checks/).*\.py$' <<<"$staged" || true)
test_count=0
impl_count=0
[[ -n "$test_staged" ]] && test_count=$(wc -l <<<"$test_staged")
[[ -n "$impl_staged" ]] && impl_count=$(wc -l <<<"$impl_staged")
if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: check-changed: Red-mode shape detected; Red-Green-Replay records the staged failure"
    exit 0
fi

mapfile -t changed < <(just changed-files)
if [[ "${#changed[@]}" -eq 0 ]]; then
    echo ":: check-changed: no changed .py vs origin/master (and none staged); nothing to gate"
    echo ":: the authoritative full gate remains 'just check' (run at pre-push + CI)"
    exit 0
fi
echo ":: check-changed: scoping the test subset + per-file coverage gate to ${#changed[@]} changed .py:"
printf '   %s\n' "${changed[@]}"
echo ":: INNER-LOOP ONLY - 'just check' runs the FULL suite/AST scans at pre-push + CI"
just check-check-coverage-incremental --paths "${changed[@]}"

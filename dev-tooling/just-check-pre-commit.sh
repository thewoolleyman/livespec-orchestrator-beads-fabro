#!/usr/bin/env bash
set -euo pipefail

# `check-master-ci-green` is an ENVIRONMENTAL gate, and inside a Fabro sandbox
# it refuses commits for a condition the staged tree cannot cause or cure:
# master CI re-queues on every merge, so with many sessions merging per hour the
# aggregate is frequently red, queued or running, and the sandbox carries a
# GitHub token so the check ENFORCES rather than warning. The refusal then lands
# on the sandbox's own Red and Green commits and on the engine's checkpoint
# commits alike — measured 2026-10-12, 5 of 27 hp checkpoint-commit failures
# since 2026-10-09 named this target, two of them alone (work-item
# bd-ib-hot3g6). Whether a run may START against a red master is already
# governed by the dispatch-time master-CI preflight, so skipping it here removes
# a duplicate signal rather than an only one.
#
# The marker is the RESOLVED sandbox-exemption key, read literally for the same
# reason the commit-refuse hook body reads it literally: the integration
# contract closes `dispatcher.sandbox_exempt_marker` to the single value
# `livespec.sandboxExempt`, so a declared alternate would be set by the
# projection and honored by nothing. A checkout WITHOUT the marker — every
# human worktree — keeps the gate exactly as it was.
sandbox_skips=()
if [[ "$(git config --get --bool livespec.sandboxExempt || printf 'false')" == true ]]; then
    echo ":: sandbox-exemption marker livespec.sandboxExempt is true: skipping check-master-ci-green"
    echo ":: the dispatch-time master-CI preflight governs whether a run may start against a red master"
    sandbox_skips+=(check-master-ci-green)
fi

staged=$(git diff --cached --name-only --diff-filter=AM)
py_staged=$(echo "$staged" | grep -E '\.py$' || true)
test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
impl_staged=$(echo "$staged" | grep -E '^(\.claude-plugin/scripts/|dev-tooling/checks/).*\.py$' || true)
test_count=0
impl_count=0
[[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
[[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)
if [[ -z "$py_staged" ]]; then
    echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
    echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
    just check-pre-commit-doc-only
    exit $?
fi
if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: Red-mode shape detected: $test_staged"
    echo ":: skipping coverage gates and same-repo live TUI picker gate in pre-commit"
    # check-check-coverage-incremental belongs in this skip list even though it
    # is vacuous on a FRESH branch: on a branch that already carries impl
    # commits, its incremental scope includes those impl files, so it RUNS the
    # branch's tests — the staged Red test among them. That test fails BY
    # DESIGN, which is the whole point of a Red commit, so leaving the gate
    # armed here refuses the ritual's own first step (work-item bd-ib-c4sfpr).
    # No coverage is lost: the Green amend, pre-push, and CI each run the full
    # aggregate on the final commit, which is the load-bearing net.
    just check-skipping \
        check-coverage \
        check-per-file-coverage \
        check-check-coverage-incremental \
        check-codex-skill-picker \
        "${sandbox_skips[@]}"
    exit $?
fi
head_msg=$(git log -1 --format=%B 2>/dev/null || true)
if [[ "$impl_count" -ge 1 ]] \
    && grep -q 'TDD-Red-Test-File-Checksum:' <<<"$head_msg" \
    && ! grep -q 'TDD-Green-Verified-At:' <<<"$head_msg"; then
    echo ":: Green-amend shape detected (impl staged; HEAD carries Red-only trailers)"
    echo ":: skipping no-arg check-red-green-replay and same-repo live TUI picker gate"
    just check-skipping check-red-green-replay check-codex-skill-picker "${sandbox_skips[@]}"
    exit $?
fi
echo ":: pre-push: skipping same-repo live TUI picker gate; run just check-codex-skill-picker explicitly for live Codex picker acceptance"
just check-skipping check-codex-skill-picker "${sandbox_skips[@]}"

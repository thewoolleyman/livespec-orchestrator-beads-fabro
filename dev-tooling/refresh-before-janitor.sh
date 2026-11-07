#!/usr/bin/env bash
# Refresh a factory run before its one declared janitor aggregate.  A preserved
# publish branch needs a merge commit, but Git's commit hooks see the merge
# index as product work and would otherwise run a second suite.  Keep that
# index staged while the janitor aggregate judges it, then record the exact
# aggregate result for the hooks to reuse when materialising the merge commit.
set -uo pipefail

default_branch="$1"
check_suite="$2"
pre_refresh="$(git rev-parse HEAD)" || exit $?
state="$(git rev-parse --git-path livespec-publication)" || exit $?
mkdir -p "$state"
if grep -qx 'stage: janitor' "$state/livespec-refresh-repair-brief" 2>/dev/null; then
    rm -f "$state/livespec-refresh-repair-brief"
fi

git fetch origin "$default_branch" --quiet
status=$?
if test "$status" -ne 0; then
    echo "LIVESPEC_JANITOR_REFRESH_FAILED: origin/$default_branch could not be fetched before the declared check suite, so the run cannot establish the tree the aggregate would grade" >&2
    exit "$status"
fi
refresh_target="$(git rev-parse "origin/$default_branch")"
status=$?
if test "$status" -ne 0; then
    echo "LIVESPEC_JANITOR_REFRESH_FAILED: origin/$default_branch could not be resolved before the declared check suite" >&2
    exit "$status"
fi

preserve_remote_ancestry=false
branch="${LIVESPEC_PUBLISH_BRANCH:-}"
if test -n "$branch"; then
    remote_line="$(git ls-remote --heads origin "refs/heads/$branch")"
    status=$?
    if test "$status" -ne 0; then
        echo "LIVESPEC_JANITOR_REFRESH_FAILED: origin could not be queried for the existing publish branch $branch before the declared check suite" >&2
        exit "$status"
    fi
    remote_tip=${remote_line%%[[:space:]]*}
    if test -n "$remote_tip"; then
        git fetch origin "refs/heads/$branch" --quiet
        status=$?
        if test "$status" -ne 0; then
            echo "LIVESPEC_JANITOR_REFRESH_FAILED: origin/$branch could not be fetched before the declared check suite" >&2
            exit "$status"
        fi
        if git merge-base --is-ancestor "$remote_tip" HEAD; then
            preserve_remote_ancestry=true
        else
            status=$?
            if test "$status" -ne 1; then
                echo "LIVESPEC_JANITOR_REFRESH_FAILED: ancestry of origin/$branch could not be resolved before the declared check suite" >&2
                exit "$status"
            fi
        fi
    fi
fi

merge_pending=false
if test "$preserve_remote_ancestry" = true; then
    LIVESPEC_FACTORY_REFRESH_MERGE=true git merge --no-commit --no-ff "$refresh_target"
    status=$?
    if test "$status" -eq 0 && test -f "$(git rev-parse --git-path MERGE_HEAD)"; then
        merge_pending=true
    fi
else
    git rebase "$refresh_target"
    status=$?
fi

if test "$status" -ne 0; then
    conflicted="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
    applying="$(git rev-parse --verify --quiet REBASE_HEAD || git rev-parse --verify --quiet MERGE_HEAD || printf '%s' "$pre_refresh")"
    git rebase --abort >/dev/null 2>&1 || true
    git merge --abort >/dev/null 2>&1 || true
    git reset --keep "$pre_refresh" >/dev/null 2>&1 || true
    repair_count="$(cat "$state/livespec-refresh-repair-count" 2>/dev/null || echo 0)"
    case "$repair_count" in ''|*[!0-9]*) repair_count=0 ;; esac
    {
        printf 'LIVESPEC_REFRESH_REPAIR_BRIEF\n'
        printf 'stage: janitor\n'
        printf 'pre-refresh-head: %s\n' "$pre_refresh"
        printf 'refresh-target: %s\n' "$refresh_target"
        printf 'run-commit: %s\n' "$applying"
        printf 'conflicted-paths: %s\n' "$conflicted"
    } > "$state/livespec-refresh-repair-brief"
    printf '%s\n' "$((repair_count + 1))" > "$state/livespec-refresh-repair-count"
    echo "LIVESPEC_REFRESH_REPAIR: janitor restored $pre_refresh after a pre-aggregate refresh conflict and recorded the repair brief for fix" >&2
    exit "$status"
fi

if ! python3 "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-run-plugin-gate.py"; then
    echo 'LIVESPEC_JANITOR_PLUGIN_GATE_FAILED: the sandbox plugin registry names a build whose cache this run could not repair, so the declared check suite would resolve a plugin root that does not exist; failing closed before running it' >&2
    exit 1
fi

gate_out="$(eval "$check_suite" 2>&1)"
gate_status=$?
printf '%s\n' "$gate_out"
if test "$gate_status" -ne 0; then
    if test "$merge_pending" = true || test "$(git rev-parse HEAD)" != "$pre_refresh"; then
        gate_targets="$(printf '%s\n' "$gate_out" | tail -c 2000 | tr '\n' ' ')"
        git rebase --abort >/dev/null 2>&1 || true
        git merge --abort >/dev/null 2>&1 || true
        git reset --keep "$pre_refresh" >/dev/null 2>&1 || true
        repair_count="$(cat "$state/livespec-refresh-repair-count" 2>/dev/null || echo 0)"
        case "$repair_count" in ''|*[!0-9]*) repair_count=0 ;; esac
        {
            printf 'LIVESPEC_REFRESH_REPAIR_BRIEF\n'
            printf 'stage: janitor\n'
            printf 'pre-refresh-head: %s\n' "$pre_refresh"
            printf 'refresh-target: %s\n' "$refresh_target"
            printf 'run-commit: %s\n' "$pre_refresh"
            printf 'failed-gate-targets: %s\n' "$gate_targets"
        } > "$state/livespec-refresh-repair-brief"
        printf '%s\n' "$((repair_count + 1))" > "$state/livespec-refresh-repair-count"
        echo "LIVESPEC_REFRESH_REPAIR: janitor restored $pre_refresh after the refreshed head's declared gate failed and recorded the repair brief for fix" >&2
    fi
    exit "$gate_status"
fi

if test "$merge_pending" = true; then
    aggregate_output="$(mktemp)"
    printf '%s\n' "$gate_out" > "$aggregate_output"
    if ! LIVESPEC_FACTORY_REFRESH_MERGE=true bash dev-tooling/record-refresh-merge-evidence.sh "$aggregate_output"; then
        status=$?
        rm -f "$aggregate_output"
        git merge --abort >/dev/null 2>&1 || true
        git reset --keep "$pre_refresh" >/dev/null 2>&1 || true
        echo "LIVESPEC_JANITOR_REFRESH_FAILED: the passed refreshed aggregate could not be recorded for its merge commit hooks" >&2
        exit "$status"
    fi
    rm -f "$aggregate_output"
    GIT_EDITOR=true LIVESPEC_FACTORY_REFRESH_MERGE=true git commit --no-edit
    status=$?
    if test "$status" -ne 0; then
        git merge --abort >/dev/null 2>&1 || true
        git reset --keep "$pre_refresh" >/dev/null 2>&1 || true
        echo "LIVESPEC_JANITOR_REFRESH_FAILED: the refresh merge commit was refused after its aggregate passed" >&2
        exit "$status"
    fi
fi

rm -f "$state/livespec-fix-no-progress-head" "$state/livespec-fix-no-progress-repeated-janitor-failure" "$state/livespec-janitor-failed-head"
git rev-parse HEAD > "$state/livespec-janitor-passed-head"
echo "LIVESPEC_JANITOR_REFRESH: pre_refresh=$pre_refresh refreshed_head=$(git rev-parse HEAD)" >&2

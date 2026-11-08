#!/usr/bin/env bash
# Refresh a factory run before its one declared janitor aggregate.  A preserved
# publish branch needs a merge commit, but Git's commit hooks see the merge
# index as product work and would otherwise run a second suite.  Keep that
# index staged while the janitor aggregate judges it, then record the exact
# aggregate result for the hooks to reuse when materialising the merge commit.
set -uo pipefail

default_branch="$1"
check_suite="$2"
if [[ "${check_suite:0:1}" == "'" && "${check_suite: -1}" == "'" ]]; then
    check_suite="${check_suite#\'}"
    check_suite="${check_suite%\'}"
fi
pre_refresh="$(git rev-parse HEAD)" || exit $?
state="$(git rev-parse --git-path livespec-publication)" || exit $?
mkdir -p "$state"
if grep -qx 'stage: janitor' "$state/livespec-refresh-repair-brief" 2>/dev/null; then
    rm -f "$state/livespec-refresh-repair-brief"
fi

restore_pre_refresh() {
    git rebase --abort >/dev/null 2>&1 || true
    git merge --abort >/dev/null 2>&1 || true
    git reset --keep "$pre_refresh" >/dev/null 2>&1 || true
}

# Writes the janitor's refresh-repair brief; the arguments after the run commit
# are the brief's remaining lines, printed verbatim.
write_repair_brief() {
    local run_commit="$1"
    shift
    local repair_count
    repair_count="$(cat "$state/livespec-refresh-repair-count" 2>/dev/null || echo 0)"
    case "$repair_count" in ''|*[!0-9]*) repair_count=0 ;; esac
    {
        printf 'LIVESPEC_REFRESH_REPAIR_BRIEF\n'
        printf 'stage: janitor\n'
        printf 'pre-refresh-head: %s\n' "$pre_refresh"
        printf 'refresh-target: %s\n' "$refresh_target"
        printf 'run-commit: %s\n' "$run_commit"
        printf '%s\n' "$@"
    } > "$state/livespec-refresh-repair-brief"
    printf '%s\n' "$((repair_count + 1))" > "$state/livespec-refresh-repair-count"
}

# A refresh step (rebase, no-commit merge, or the merge commit through its
# hooks) failed with status $1 and output $2: restore the pre-refresh head and
# route a conflict or a hook refusal to fix through a brief.
fail_refresh() {
    local status="$1" refresh_out="$2"
    local conflicted applying hook_out hook_marker hook_targets hook_tail
    conflicted="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
    applying="$(git rev-parse --verify --quiet REBASE_HEAD || git rev-parse --verify --quiet MERGE_HEAD || printf '%s' "$pre_refresh")"
    hook_out="$(printf '%s\n' "$refresh_out" | awk -v ORS= '/^(Not committing merge|error: could not commit staged changes|error: could not apply|error: .* hook failed|Could not apply)/ { pending = pending $0 RS; diag = 1; next } diag && (/^hint:/ || /^$/) { pending = pending $0 RS; next } { print pending $0 RS; pending = ""; diag = 0 }')"
    hook_targets=
    case "$refresh_out" in
        *'Failed targets'*)
            hook_marker="${refresh_out#*Failed targets}"
            hook_targets="$(printf '%s\n' "$hook_marker" | grep '^  - ' | cut -c5- | tr '\n' ' ' | sed 's/ $//')"
            ;;
    esac
    restore_pre_refresh
    if test -z "$conflicted" && test -n "$hook_targets"; then
        hook_tail="$(printf '%s\n' "$hook_out" | tail -n 80)"
        write_repair_brief "$applying" "failed-hook-targets: $hook_targets" "hook-output-last-80-lines:" "$hook_tail"
        echo "LIVESPEC_REFRESH_REPAIR: janitor restored $pre_refresh after its refresh commit hook refused and recorded the repair brief for fix" >&2
        exit "$status"
    fi
    if test -n "$conflicted"; then
        write_repair_brief "$applying" "conflicted-paths: $conflicted"
        echo "LIVESPEC_REFRESH_REPAIR: janitor restored $pre_refresh after a pre-aggregate refresh conflict and recorded the repair brief for fix" >&2
        exit "$status"
    fi
    echo "LIVESPEC_JANITOR_REFRESH_FAILED: this run could not be refreshed onto origin/$default_branch and no path conflicted or commit hook named failed targets, so the refresh was undone and this working branch is restored to its pre-refresh head $pre_refresh; failing closed before the declared check suite" >&2
    exit "$status"
}

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
    refresh_out="$(LIVESPEC_FACTORY_REFRESH_MERGE=true git merge --no-commit --no-ff "$refresh_target" 2>&1)"
    status=$?
else
    refresh_out="$(git rebase "$refresh_target" 2>&1)"
    status=$?
fi
printf '%s\n' "$refresh_out" >&2
if test "$status" -ne 0; then
    fail_refresh "$status" "$refresh_out"
fi
if test "$preserve_remote_ancestry" = true && test -f "$(git rev-parse --git-path MERGE_HEAD)"; then
    merge_pending=true
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
        restore_pre_refresh
        write_repair_brief "$pre_refresh" "failed-gate-targets: $gate_targets"
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
        restore_pre_refresh
        echo "LIVESPEC_JANITOR_REFRESH_FAILED: the passed refreshed aggregate could not be recorded for its merge commit hooks" >&2
        exit "$status"
    fi
    rm -f "$aggregate_output"
    commit_out="$(GIT_EDITOR=true LIVESPEC_FACTORY_REFRESH_MERGE=true git commit --no-edit 2>&1)"
    status=$?
    printf '%s\n' "$commit_out" >&2
    if test "$status" -ne 0; then
        fail_refresh "$status" "$commit_out"
    fi
fi

rm -f "$state/livespec-fix-no-progress-head" "$state/livespec-fix-no-progress-repeated-janitor-failure" "$state/livespec-janitor-failed-head"
git rev-parse HEAD > "$state/livespec-janitor-passed-head"
echo "LIVESPEC_JANITOR_REFRESH: pre_refresh=$pre_refresh refreshed_head=$(git rev-parse HEAD)" >&2

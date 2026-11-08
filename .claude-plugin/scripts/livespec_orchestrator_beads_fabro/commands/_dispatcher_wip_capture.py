"""Dispatcher-materialized capture program for a run's settled work.

The workflow invokes this program after every committing settle step.  It lives
outside the run worktree with the push credential helper, so a stage cannot
replace the code that chooses or publishes a recovery ref.
"""

from __future__ import annotations

__all__: list[str] = ["WIP_CAPTURE_PROGRAM_FILENAME", "wip_capture_program_source"]

WIP_CAPTURE_PROGRAM_FILENAME = "livespec-capture-wip"


def wip_capture_program_source() -> str:
    """Return the hookless, immutable work-in-progress capture program."""
    return r"""#!/usr/bin/env bash
set -u
item=${1:-}
run=${2:-}
default_branch=${3:-}
if test -z "$item" || test -z "$run" || test -z "$default_branch"; then
    echo 'LIVESPEC_WIP_CAPTURE_FAILED: ref=unresolved tip=unresolved' \
        'reason=item, run, or default branch is absent' >&2
    exit 0
fi
branch="refs/heads/fabro/run/$run"
tip=$(git rev-parse --verify "$branch" 2>/dev/null) || {
    echo "LIVESPEC_WIP_CAPTURE_FAILED: ref=refs/livespec/wip/$item/$run/unresolved" \
        "tip=unresolved reason=run branch $branch is absent" >&2
    exit 0
}
tip_tree=$(git rev-parse "$tip^{tree}" 2>/dev/null) || {
    echo "LIVESPEC_WIP_CAPTURE_FAILED: ref=refs/livespec/wip/$item/$run/unresolved" \
        "tip=$tip reason=tip tree is unreadable" >&2
    exit 0
}
base=$(git merge-base "$tip" "refs/remotes/origin/$default_branch" 2>/dev/null) || base=''
base_tree=''
if test -n "$base"; then base_tree=$(git rev-parse "$base^{tree}" 2>/dev/null || true); fi
default_tree=$(git rev-parse "refs/remotes/origin/$default_branch^{tree}" 2>/dev/null || true)
prefix="refs/livespec/wip/$item/$run/"
refs=$(git ls-remote origin "${prefix}*" 2>/dev/null) || {
    echo "LIVESPEC_WIP_CAPTURE_FAILED: ref=${prefix}unresolved tip=$tip" \
        'reason=origin work-in-progress refs are unreadable' >&2
    exit 0
}
highest=0
highest_tip=''
while IFS=$'\t' read -r remote_tip remote_ref; do
    ordinal=${remote_ref#"$prefix"}
    case "$ordinal" in ''|*[!0-9]*) continue ;; esac
    if test "$ordinal" -gt "$highest"; then highest=$ordinal; highest_tip=$remote_tip; fi
done <<< "$refs"
next=$((highest + 1))
ref="${prefix}${next}"
if test "$tip_tree" = "$base_tree" || test "$tip_tree" = "$default_tree"; then
    echo "LIVESPEC_WIP_SKIPPED: $ref $tip tree carries none of the run work" >&2
    exit 0
fi
if test -n "$highest_tip" && test "$tip" = "$highest_tip"; then
    echo "LIVESPEC_WIP_SKIPPED: ${prefix}${highest} $tip already captured" >&2
    exit 0
fi
if test "${4:-}" = '--print-refspec'; then
    echo "LIVESPEC_WIP_CAPTURE_READY: $ref $tip" >&2
    exit 0
fi
root=${LIVESPEC_SANDBOX_GH_REFRESH_ROOT:-/workspace/.livespec-gh-refresh}
push="$root/bin/push_origin"
if test -x "$push"; then
    runner=("$push")
elif test -n "${GITHUB_APP_ID:-}"; then
    echo "LIVESPEC_WIP_CAPTURE_FAILED: ref=$ref tip=$tip" \
        'reason=Dispatcher materialized push helper is absent' >&2
    exit 0
else
    runner=()
fi
if "${runner[@]}" env GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_NOSYSTEM=1 git -c core.hooksPath=/dev/null push origin "$tip:$ref"; then
    echo "LIVESPEC_WIP_CAPTURED: $ref $tip" >&2
else
    echo "LIVESPEC_WIP_CAPTURE_FAILED: ref=$ref tip=$tip" \
        'reason=hookless preservation push failed' >&2
fi
exit 0
"""

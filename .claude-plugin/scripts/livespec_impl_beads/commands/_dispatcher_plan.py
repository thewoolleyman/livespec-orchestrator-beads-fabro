"""Pure planning layer for the Dispatcher: plans, argv builders, parsers.

Everything here is a pure function of its inputs so the hermetic test
tier covers the Dispatcher's decision surface without subprocesses. The
side-effecting execution of these argvs lives in `_dispatcher_engine`
(sequencing) and `_dispatcher_io` (the subprocess seam).

The argv builders encode the family discipline the interim
`/livespec-orchestrate` driver documents (livespec
non-functional-requirements.md §"Orchestrator-internal Dispatcher
guidance"): secondary worktree off fresh `origin/master`, `mise exec --
git ...` so hooks fire, `gh pr view` for merge confirmation, the janitor
argv injected from configuration (never hardcoded), and worktree removal
only after the merge is CONFIRMED.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_impl_beads.types import WorkItem

__all__: list[str] = [
    "DispatchPlan",
    "PrView",
    "build_plan",
    "fabro_run_argv",
    "fetch_argv",
    "janitor_argv_with_default",
    "mise_trust_argv",
    "parse_pr_view",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "pull_primary_argv",
    "render_goal",
    "worktree_add_argv",
    "worktree_remove_argv",
]

_DEFAULT_JANITOR: tuple[str, ...] = ("mise", "exec", "--", "just", "check")


@dataclass(frozen=True, kw_only=True)
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front."""

    repo: Path
    work_item_id: str
    branch: str
    worktree: Path
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    janitor: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on."""

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None


def build_plan(
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    janitor: tuple[str, ...] | None,
) -> DispatchPlan:
    """Resolve the per-item dispatch plan (branch, worktree, argv config)."""
    return DispatchPlan(
        repo=repo,
        work_item_id=work_item_id,
        branch=f"fabro/{work_item_id}",
        worktree=repo / "worktrees" / f"fabro-{work_item_id}",
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        fabro_bin=fabro_bin,
        janitor=janitor_argv_with_default(janitor=janitor),
    )


def janitor_argv_with_default(*, janitor: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the configured janitor argv, defaulting to `mise exec -- just check`."""
    if janitor is None or len(janitor) == 0:
        return _DEFAULT_JANITOR
    return janitor


def render_goal(*, item: WorkItem, repo: Path, branch: str) -> str:
    """Render the per-item brief delivered to the phase graph as the run goal.

    Item specifics ONLY: the durable family discipline (Red-Green-Replay,
    hook rules, PR/merge protocol) lives in the versioned prompt files of
    the phase graph, not here.
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    return (
        f"Work-item: {item.id}\n"
        f"Repo: {repo}\n"
        f"Branch (already checked out in this worktree): {branch}\n"
        f"Priority: P{item.priority}  Type: {item.type}\n"
        f"{gap_line}"
        f"Title: {item.title}\n"
        "\n"
        "Description:\n"
        f"{item.description}\n"
    )


def fetch_argv(*, plan: DispatchPlan) -> list[str]:
    return ["git", "-C", str(plan.repo), "fetch", "origin"]


def worktree_add_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "add",
        str(plan.worktree),
        "-b",
        plan.branch,
        "origin/master",
    ]


def mise_trust_argv(*, plan: DispatchPlan) -> list[str]:
    _ = plan
    return ["mise", "trust"]


def fabro_run_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        plan.fabro_bin,
        "run",
        str(plan.workflow_toml),
        "--goal-file",
        str(plan.goal_file),
        "--no-upgrade-check",
        "-I",
        f"work_item_id={plan.work_item_id}",
        "-I",
        f"branch={plan.branch}",
    ]


def pr_view_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit",
    ]


def pr_arm_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "merge", str(number), "--rebase", "--auto", "--delete-branch"]


def pr_update_branch_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "update-branch", str(number)]


def pull_primary_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "mise",
        "exec",
        "--",
        "git",
        "-C",
        str(plan.repo),
        "pull",
        "--ff-only",
        "origin",
        "master",
    ]


def worktree_remove_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "remove",
        str(plan.worktree),
    ]


def parse_pr_view(*, stdout: str) -> PrView | None:
    """Parse `gh pr view --json` output; None when the shape is unusable."""
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    number_raw: object = parsed.get("number")
    if not isinstance(number_raw, int):
        return None
    state_raw: object = parsed.get("state")
    state = state_raw if isinstance(state_raw, str) else "UNKNOWN"
    merge_state_raw: object = parsed.get("mergeStateStatus")
    merge_state = merge_state_raw if isinstance(merge_state_raw, str) else "UNKNOWN"
    return PrView(
        number=number_raw,
        state=state,
        auto_merge_armed=parsed.get("autoMergeRequest") is not None,
        merge_state_status=merge_state,
        merge_sha=_merge_sha_of(parsed=parsed),
    )


def _merge_sha_of(*, parsed: dict[str, Any]) -> str | None:
    commit_raw: object = parsed.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    commit = cast("dict[str, Any]", commit_raw)
    oid_raw: object = commit.get("oid")
    if isinstance(oid_raw, str) and oid_raw:
        return oid_raw
    return None

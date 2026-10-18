"""Merged-PR resolution for the reconcile-merged operator valve.

Split out of `_dispatcher_reconcile_merged` along its cohesion seam: that
module is the command supervisor (preflight, journal, janitor, acceptance,
outcome), while this one answers a single question — WHICH merged pull request
belongs to this stranded work-item — and owns the two `gh` shapes and the
parsing that answer needs.

The answer is deliberately three-valued: a `PrView` when exactly one merged PR
matches, a refusal STRING when several do (reconciling against the wrong merge
is worse than not reconciling), and `None` when none does.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    parse_pr_view,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "merged_pr_list_argv",
    "parse_merged_pr_list",
    "resolve_merged_pr",
]

_GH_TIMEOUT_SECONDS = 120.0


def resolve_merged_pr(
    *, plan: DispatchPlan, item: WorkItem, runner: CommandRunner, journal: JournalFile
) -> PrView | str | None:
    """Resolve the merged PR for `item`: a view, a refusal string, or `None`."""
    viewed = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-view-branch",
        command=(_pr_view_branch_argv(plan=plan), plan.repo, _GH_TIMEOUT_SECONDS, None),
    )
    if viewed.exit_code == 0:
        return _merged_pr_view(stdout=viewed.stdout)
    # The base branch is read off the plan's ONE resolved contract. Pinning the
    # search to a branch name this fleet happens to use searched an adopter's
    # forge for merges onto a branch they do not have -- a clean, plausible,
    # empty result, reported as "no merged PR belongs to this item".
    default_branch = plan.integration.contract.default_branch
    searched = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-list-merged",
        command=(
            merged_pr_list_argv(item=item, default_branch=default_branch),
            plan.repo,
            _GH_TIMEOUT_SECONDS,
            None,
        ),
    )
    candidates = parse_merged_pr_list(
        stdout=searched.stdout,
        item=item,
        branch=plan.branch,
        default_branch=default_branch,
    )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return _ambiguous_pr_detail(candidates=candidates)
    return None


def merged_pr_list_argv(*, item: WorkItem, default_branch: str) -> list[str]:
    """Build the GitHub search argv used when branch lookup is unavailable.

    `default_branch` is the RESOLVED default branch of the governed repository,
    never a branch name this fleet happens to use: the search pins `--base`, so a
    constant there asks an adopter's forge about merges onto a branch they do not
    have and gets an empty, error-free, wrong answer.
    """
    return [
        "gh",
        "pr",
        "list",
        "--state",
        "merged",
        "--search",
        item.id,
        "--json",
        "number,title,body,headRefName,baseRefName,state,mergeCommit",
        "--base",
        default_branch,
        "--limit",
        "20",
    ]


def parse_merged_pr_list(
    *, stdout: str, item: WorkItem, branch: str, default_branch: str
) -> tuple[PrView, ...]:
    """Parse merged PR search results, accepting either branch or title/id matches.

    A candidate merged onto some OTHER base than `default_branch` is rejected,
    which is what stops a reconcile from disposing an item against a merge into
    someone's long-lived side branch. The branch it compares against is resolved
    for the same reason the search's own `--base` is.
    """
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure) or not isinstance(parsed_raw, list):
        return ()
    matches: list[PrView] = []
    body_matches: list[PrView] = []
    for entry_raw in cast("list[object]", parsed_raw):
        view = _pr_view_from_list_entry(
            entry_raw=entry_raw, item=item, branch=branch, default_branch=default_branch
        )
        if view is not None:
            matches.append(view)
            body_raw: object = cast("dict[str, Any]", entry_raw).get("body")
            if isinstance(body_raw, str) and item.id in body_raw:
                body_matches.append(view)
    return (body_matches[0],) if body_matches else tuple(matches)


def _ambiguous_pr_detail(*, candidates: tuple[PrView, ...]) -> str:
    listed = ", ".join(f"#{candidate.number} {candidate.merge_sha}" for candidate in candidates)
    return f"ERROR: ambiguous merged PR candidates for reconcile-merged: {listed}\n"


def _pr_view_branch_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit,statusCheckRollup",
    ]


def _merged_pr_view(*, stdout: str) -> PrView | None:
    view = parse_pr_view(stdout=stdout)
    if view is None or view.state != "MERGED" or view.merge_sha is None:
        return None  # pragma: no cover - defensive malformed gh JSON
    return view


def _pr_view_from_list_entry(
    *, entry_raw: object, item: WorkItem, branch: str, default_branch: str
) -> PrView | None:
    if not isinstance(entry_raw, dict):
        return None
    entry = cast("dict[str, Any]", entry_raw)
    number_raw: object = entry.get("number")
    state_raw: object = entry.get("state")
    if not isinstance(number_raw, int) or state_raw != "MERGED":
        return None
    title_raw: object = entry.get("title")
    head_raw: object = entry.get("headRefName")
    base_raw: object = entry.get("baseRefName")
    if isinstance(base_raw, str) and base_raw != default_branch:
        return None
    body_raw: object = entry.get("body")
    if (
        head_raw != branch
        and not (isinstance(title_raw, str) and item.id in title_raw)
        and not (isinstance(body_raw, str) and item.id in body_raw)
    ):
        return None
    merge_sha = _list_entry_merge_sha(entry=entry)
    if merge_sha is None:
        return None
    return PrView(
        number=number_raw,
        state="MERGED",
        auto_merge_armed=False,
        merge_state_status="UNKNOWN",
        merge_sha=merge_sha,
        terminal_required_check_failures=(),
    )


def _list_entry_merge_sha(*, entry: dict[str, Any]) -> str | None:
    commit_raw: object = entry.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None  # pragma: no cover - defensive malformed gh JSON
    oid_raw: object = cast("dict[str, Any]", commit_raw).get("oid")
    return oid_raw if isinstance(oid_raw, str) and oid_raw else None

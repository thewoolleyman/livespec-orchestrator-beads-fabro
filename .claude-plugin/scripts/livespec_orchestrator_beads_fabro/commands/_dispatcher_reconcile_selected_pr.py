"""Explicit pull-request selection for the reconcile-merged valve."""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    ACCEPTANCE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "acceptance_selected_pr_mismatch_refusal",
    "pr_view_from_merged_list_entry",
    "resolve_selected_pr",
]

_GH_TIMEOUT_SECONDS = 120.0


def resolve_selected_pr(
    *,
    plan: DispatchPlan,
    item: WorkItem,
    runner: CommandRunner,
    journal: JournalFile,
    selected_pr_number: int,
) -> PrView | str:
    """Resolve one selected merged head-ref or title carrier, never a body mention."""
    selected = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="reconcile-pr-view-selected",
        command=(
            [
                "gh",
                "pr",
                "view",
                str(selected_pr_number),
                "--json",
                "number,title,headRefName,baseRefName,state,mergeCommit",
            ],
            plan.repo,
            _GH_TIMEOUT_SECONDS,
            None,
        ),
    )
    candidate = pr_view_from_merged_list_entry(
        entry_raw=parse_json(text=selected.stdout),
        item=item,
        branch=plan.branch,
        default_branch=plan.integration.contract.default_branch,
    )
    if candidate is not None and candidate[1] in {"head", "title"}:
        resolved = candidate[0]
        journal.append(
            record={
                "stage": "reconcile-merged-resolution",
                "work_item_id": item.id,
                "pr_number": resolved.number,
                "merge_sha": resolved.merge_sha,
            }
        )
        return resolved
    return (
        f"ERROR: reconcile-merged --pr #{selected_pr_number} refused: pull request "
        f"#{selected_pr_number} is not a merged pull request onto "
        f"{plan.integration.contract.default_branch} that identifies work-item {item.id} "
        "by head ref or title\n"
    )


def pr_view_from_merged_list_entry(
    *, entry_raw: object, item: WorkItem, branch: str, default_branch: str
) -> tuple[PrView, str] | None:
    """Return one usable merged candidate and its strongest identifying tier."""
    if not isinstance(entry_raw, dict):
        return None
    entry = cast("dict[str, Any]", entry_raw)
    number_raw: object = entry.get("number")
    state_raw: object = entry.get("state")
    if not isinstance(number_raw, int) or state_raw != "MERGED":
        return None
    base_raw: object = entry.get("baseRefName")
    if isinstance(base_raw, str) and base_raw != default_branch:
        return None
    tier = _candidate_tier(entry=entry, item=item, branch=branch)
    merge_sha = _merge_sha(entry=entry)
    if tier is None or merge_sha is None:
        return None
    return (
        PrView(
            number=number_raw,
            state="MERGED",
            auto_merge_armed=False,
            merge_state_status="UNKNOWN",
            merge_sha=merge_sha,
        ),
        tier,
    )


def acceptance_selected_pr_mismatch_refusal(
    *, item: WorkItem, selected: PrView, journal: JournalFile
) -> str | None:
    """Refuse a selected PR that differs from the item's green janitor evidence."""
    janitor_evidence = _latest_green_janitor_evidence(item=item, journal=journal)
    if janitor_evidence is None:
        return None
    evidence_pr, evidence_sha = janitor_evidence
    if (selected.number, selected.merge_sha) == janitor_evidence:
        return None
    return (
        f"ERROR: reconcile-merged --pr selected PR #{selected.number} ({selected.merge_sha}) "
        f"does not match journaled green janitor evidence PR #{evidence_pr} ({evidence_sha}) "
        f"for work-item {item.id}; refusing before acceptance\n"
    )


def _candidate_tier(*, entry: dict[str, Any], item: WorkItem, branch: str) -> str | None:
    if entry.get("headRefName") == branch:
        return "head"
    title_raw: object = entry.get("title")
    if isinstance(title_raw, str) and item.id in title_raw:
        return "title"
    body_raw: object = entry.get("body")
    return "body" if isinstance(body_raw, str) and item.id in body_raw else None


def _merge_sha(*, entry: dict[str, Any]) -> str | None:
    commit_raw: object = entry.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    oid_raw: object = cast("dict[str, Any]", commit_raw).get("oid")
    return oid_raw if isinstance(oid_raw, str) and oid_raw else None


def _latest_green_janitor_evidence(
    *, item: WorkItem, journal: JournalFile
) -> tuple[int, str] | None:
    """Read the most recent successful post-merge janitor outcome for this item."""
    for record in reversed(read_journal_records(journal_path=journal.path)):
        outcome_raw = record.get("outcome")
        if record.get("stage") != "outcome" or not isinstance(outcome_raw, dict):
            continue
        outcome = cast("dict[str, object]", outcome_raw)
        if (
            outcome.get("work_item_id") != item.id
            or outcome.get("status") != "green"
            or outcome.get("stage") not in {"done", ACCEPTANCE_STAGE}
            or outcome.get("detail") != "merged, post-merge janitor green"
        ):
            continue
        number = outcome.get("pr_number")
        merge_sha = outcome.get("merge_sha")
        if type(number) is int and isinstance(merge_sha, str) and merge_sha:
            return number, merge_sha
    return None

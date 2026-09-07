"""Capacity attention lanes composed from dispatcher accounting."""

from __future__ import annotations

import shlex
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    ActiveClaimAccounting,
    ActiveClaimHold,
    claimed_active_projection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_WIP_CAP,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "capacity_items",
]

_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def capacity_items(*, project_root: Path, repo: str, items: list[WorkItem]) -> list[AttentionItem]:
    wip_cap = unsafe_perform_io(resolve_wip_cap(cwd=project_root).value_or(DEFAULT_WIP_CAP))
    accounting = claimed_active_projection(
        repo=project_root,
        items=items,
        journal=JournalFile(path=project_root / _DISPATCHER_JOURNAL_PATH),
    )
    counted_holds = _counted_holds(accounting=accounting)
    counted_count = accounting.active_count
    free_slots = max(0, wip_cap - counted_count)
    if free_slots > 0 or not _has_actionable_hold(holds=counted_holds):
        return []
    return [
        _aggregate_item(
            project_root=project_root,
            repo=repo,
            wip_cap=wip_cap,
            counted_count=counted_count,
        ),
        *[
            _hold_item(project_root=project_root, repo=repo, hold=hold)
            for hold in counted_holds
            if not hold.backed_by_live_watchable_run
        ],
    ]


def _counted_holds(*, accounting: ActiveClaimAccounting) -> tuple[ActiveClaimHold, ...]:
    return (
        *[
            ActiveClaimHold(
                work_item_id=work_item_id,
                reason="live-watchable-run",
                backed_by_live_watchable_run=True,
            )
            for work_item_id in accounting.live_lock_active_ids
        ],
        *accounting.actionable_holds,
    )


def _has_actionable_hold(*, holds: tuple[ActiveClaimHold, ...]) -> bool:
    return any(not hold.backed_by_live_watchable_run for hold in holds)


def _aggregate_item(
    *, project_root: Path, repo: str, wip_cap: int, counted_count: int
) -> AttentionItem:
    free_slots = max(0, wip_cap - counted_count)
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:capacity:{repo}",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Capacity reached for {repo}: {counted_count} counted claims, {free_slots} "
            f"free slots under per-repo WIP cap {wip_cap}; host-run concurrency is "
            "governed separately."
        ),
        source_ref=SourceRef(repo=repo),
        handoff=Handoff(
            kind="shell",
            command=_aggregate_command(project_root=project_root, repo=repo),
        ),
    )


def _hold_item(*, project_root: Path, repo: str, hold: ActiveClaimHold) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:capacity-hold:{hold.work_item_id}",
        kind="hygiene",
        urgency="high",
        summary=f"Inspect capacity hold {hold.work_item_id}: {hold.reason}.",
        source_ref=SourceRef(repo=repo, work_item=hold.work_item_id),
        handoff=Handoff(
            kind="shell",
            command=_hold_command(project_root=project_root, work_item_id=hold.work_item_id),
        ),
    )


def _aggregate_command(*, project_root: Path, repo: str) -> str:
    prompt = (
        f"inspect-capacity {repo} in repository {project_root}. "
        "Use the dispatcher accounting verdict as the capacity authority; "
        "host-run concurrency is governed separately."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"


def _hold_command(*, project_root: Path, work_item_id: str) -> str:
    prompt = (
        f"inspect-capacity-hold {work_item_id} in repository {project_root}. "
        "Use the dispatcher accounting evidence and decide whether a live run, "
        "journal repair, or reconcile path owns the claim; do not move status "
        "when evidence shows a merged pull request."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"

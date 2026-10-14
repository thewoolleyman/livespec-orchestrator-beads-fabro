"""Judge auto-approvals before allocating any factory capacity to them."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_pre_admission_dod import pre_admission_hold
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_valve_predicates import (
    awaits_dispatcher_admission,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "judge_auto_approvals",
]


def judge_auto_approvals(
    *, repo: Path, config: StoreConfig, candidates: list[WorkItem], journal: JournalFile
) -> tuple[list[WorkItem], list[DispatchOutcome]]:
    """Keep existing ready items, judge pending auto candidates, report holds.

    Filtering precedes slot allocation so a held, high-ranked item cannot
    consume the capacity that a lower-ranked eligible item should receive.
    """
    kept: list[WorkItem] = []
    held: list[DispatchOutcome] = []
    for item in candidates:
        reason = (
            pre_admission_hold(path=config, item=item)
            if awaits_dispatcher_admission(item=item, cwd=repo)
            else None
        )
        if reason is None:
            kept.append(item)
            continue
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="pre-admission-dod",
            pr_number=None,
            merge_sha=None,
            detail=reason,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        held.append(outcome)
    return kept, held

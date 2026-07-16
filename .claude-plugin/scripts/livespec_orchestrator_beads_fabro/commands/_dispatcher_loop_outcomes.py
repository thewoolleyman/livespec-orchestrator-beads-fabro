"""Shared outcome helpers for dispatch-loop early refusals."""

from __future__ import annotations

from dataclasses import asdict

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "failed_dispatch_outcome",
]


def failed_dispatch_outcome(
    *,
    journal: JournalFile,
    work_item_id: str,
    stage: str,
    detail: str,
) -> DispatchOutcome:
    """Create and journal a terminal failed dispatch outcome."""
    outcome = DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    return outcome

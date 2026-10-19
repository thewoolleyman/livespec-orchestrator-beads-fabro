"""Ledger disposition for a Fabro lifecycle cancel outside the watchdog."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["dispose_external_fabro_cancel"]

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def dispose_external_fabro_cancel(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Rest an externally cancelled Fabro run at blocked/needs-human.

    The progress watchdog exits before Fabro's generic terminal mapper and
    reports its own status, so this predicate cannot reclassify a watchdog
    cancellation. An engine lifecycle reason of `cancelled` reaching here was
    therefore supplied by an operator or another client and requires a human
    decision before another dispatch.
    """
    if outcome.status != "cancelled":
        return
    blocked = attempt(
        action=lambda: update_work_item_blocked_state(
            path=store_config(repo=repo),
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
            admission_policy="manual",
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(blocked, AttemptFailure):
        journal.append(
            record={
                "stage": "fabro-run-cancelled-blocked-error",
                "work_item_id": item.id,
                "reason": type(blocked.error).__name__,
            }
        )
        return
    commented = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item.id,
            body=_cancelled_comment(outcome=outcome),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(commented, AttemptFailure):
        journal.append(
            record={
                "stage": "fabro-run-cancelled-comment-error",
                "work_item_id": item.id,
                "reason": type(commented.error).__name__,
            }
        )
        return
    journal.append(
        record={
            "stage": "fabro-run-cancelled-blocked",
            "work_item_id": item.id,
            "run_id": outcome.fabro_run_id,
            "factory": outcome.fabro_factory_name,
            "reason": "needs-human",
        }
    )


def _cancelled_comment(*, outcome: DispatchOutcome) -> str:
    """Render the append-only operator record before attempting its write."""
    return (
        "livespec-fabro-run-cancelled\n\n"
        f"cancelled run id: {outcome.fabro_run_id}\n"
        f"factory: {outcome.fabro_factory_name}\n\n"
        "The Fabro engine ended this run with lifecycle reason `cancelled` outside "
        "the Dispatcher progress watchdog. The item rests at blocked / needs-human; "
        f"triage it, then release with `resolve-blocked:{outcome.work_item_id}:ready`."
    )

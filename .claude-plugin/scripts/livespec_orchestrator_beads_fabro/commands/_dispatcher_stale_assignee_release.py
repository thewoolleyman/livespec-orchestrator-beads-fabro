"""Whether a `ready` item is a stale assignee whose run stamp names a run.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" releases an item for recovery
"while it is a stale assignee whose run stamp names a run", whether or not a
reconciliation pass has yet cleared it. That is the half of the release the
journal cannot carry: a held stale assignee has no `stale-assignee-clear` row,
yet "a held stale assignee whose run stamp names a run remains released for
recovery, so the safety of its next dispatch is decided by recovery routing's own
measurements, not by this hold".

A PENDING STAMP, AN UNREADABLE STAMP AND NO STAMP ARE NOT RELEASED. Each names no
run for recovery routing to measure, so the item is admitted as any `ready` item
is and "its next admission replaces its stamp exactly as any admission of a
`ready` item does". An unreadable ledger row is the same answer: the item was
read moments earlier to become a candidate, and a failed second read releases
nothing rather than routing a dispatch on a claim nobody could attribute.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_claim import claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    LEDGER_WRITE_ERRORS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "stale_assignee_with_run",
]

_READY_STATUS = "ready"
_FABRO_ASSIGNEE = "fabro"


def stale_assignee_with_run(*, repo: Path, item: WorkItem) -> bool:
    """Whether this candidate is a `ready` item assigned `fabro` and stamped with a run."""
    if item.status != _READY_STATUS or item.assignee != _FABRO_ASSIGNEE:
        return False
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=item.id),
        exceptions=LEDGER_WRITE_ERRORS,
    )
    if isinstance(row, AttemptFailure):
        return False
    return row.stamp is not None and not row.stamp.pending

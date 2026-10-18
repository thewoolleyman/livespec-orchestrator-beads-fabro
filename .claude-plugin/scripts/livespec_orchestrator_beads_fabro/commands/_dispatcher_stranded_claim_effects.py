"""The ledger reads and writes one claim recovery performs, as one unit.

Split out of `_dispatcher_stranded_claim_recovery` by cohesion. That module
owns the ORDER — record, then comment, then transition, with a re-read
immediately before the last — and this owns the four acts that order is over.
The split is what lets a reader check the ordering guarantee without reading
four `attempt` ladders, and lets each act's failure mode be asserted without
driving the sequence.

EVERY ACT IS THREE-VALUED OR BOOLEAN AND NONE OF THEM RAISES. A recovery runs
inside a reconciliation pass that must not die on one unreachable tenant, and
each failure here means the same thing to its caller: the effect could not be
established, so nothing further may be written and the claim is held. The two
READS answer `None` for "could not be read"; the two WRITES answer `False`.

THE TRANSITIONS ARE THE SHARED SEAMS, NOT NEW ONES. The release goes through
`update_work_item_status` with `clear_assignee=True` — the same seam the
pre-run and the stall releases use — so a released stranded claim leaves the
ledger in one shape rather than a third that merely looks like the other two.
The repeat goes through `update_work_item_blocked_state`, which REPLACES the
blocked-reason label rather than adding one beside it, and sets
`admission:manual` so nothing automatic leaves that state.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import update_work_item_status

__all__: list[str] = [
    "append_claim_comment",
    "claim_row",
    "claim_unchanged",
    "release_claim_to_ready",
    "rest_claim_for_a_human",
]

_ACTIVE_STATUS = "active"
_FABRO_ASSIGNEE = "fabro"
_READY_STATUS = "ready"
_BLOCKED_STATUS = "blocked"
_NEEDS_HUMAN_REASON = "needs-human"
_MANUAL_ADMISSION = "manual"

_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def claim_row(*, repo: Path, work_item_id: str) -> ClaimRow | None:
    """One item's status, assignee and claim stamp, or None when unreadable."""
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=work_item_id),
        exceptions=_LEDGER_ERRORS,
    )
    return None if isinstance(row, AttemptFailure) else row


def claim_unchanged(*, row: ClaimRow, run_id: str) -> bool:
    """Whether this row still carries the claim a recovery is recovering.

    All three conditions the clause names, in one predicate: still `active`,
    still assigned `fabro`, and still stamped — not PENDING — with the same
    run. A pending stamp fails it, which is what keeps a freshly admitted
    dispatch's claim from being overwritten by a recovery of the run it
    replaced.
    """
    if row.status != _ACTIVE_STATUS or row.assignee != _FABRO_ASSIGNEE:
        return False
    stamp = row.stamp
    return stamp is not None and not stamp.pending and stamp.run_id == run_id


def append_claim_comment(*, repo: Path, work_item_id: str, body: str) -> bool:
    """Append one durable account to the item, reporting whether it landed."""
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo), work_item_id=work_item_id, body=body
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return not isinstance(written, AttemptFailure)


def release_claim_to_ready(*, repo: Path, work_item_id: str) -> bool:
    """Return the item to `ready` with its `fabro` claim dropped."""
    applied = attempt(
        action=lambda: update_work_item_status(
            path=store_config(repo=repo),
            item_id=work_item_id,
            status=_READY_STATUS,
            clear_assignee=True,
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return not isinstance(applied, AttemptFailure)


def rest_claim_for_a_human(*, repo: Path, work_item_id: str) -> bool:
    """Rest the item at `blocked` / `needs-human`, admission `manual`."""
    rested = attempt(
        action=lambda: update_work_item_blocked_state(
            path=store_config(repo=repo),
            item_id=work_item_id,
            status=_BLOCKED_STATUS,
            blocked_reason=_NEEDS_HUMAN_REASON,
            admission_policy=_MANUAL_ADMISSION,
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return not isinstance(rested, AttemptFailure)

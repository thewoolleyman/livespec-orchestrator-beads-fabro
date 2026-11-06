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
READS answer `None` for "could not be read". The comment write answers `False`.
The two TRANSITIONS answer `None` when they landed and otherwise the HOLD the
claim must be reported under, because a transition can now fail in two ways
that are not the same finding.

THE TRANSITIONS ARE THE SHARED SEAMS, NOT NEW ONES. The release goes through
`update_work_item_status` with `clear_assignee=True` — the same seam the
pre-run and the stall releases use — so a released stranded claim leaves the
ledger in one shape rather than a third that merely looks like the other two.
The repeat goes through `update_work_item_blocked_state`, which REPLACES the
blocked-reason label rather than adding one beside it. The blocked status and
recorded reason are the hold; recovery never writes an admission label.

BOTH TRANSITIONS ARE CLAIM-CHANGING WRITES, so each goes through
`_dispatcher_claim_writes`. With `dispatcher.claim_tokens` true a recovery
writes the item only after winning its current claim token. A recovery that
loses it has written nothing to the item and holds the claim as
`claim-changed`: another writer changed the claim, which is the same finding
the stamp re-read reports and has the same remedy. Every other way the write
can fail to land (a ledger fault, a token whose outcome cannot be read, a
transition still pending, an expired lease, an item naming no token) is
`effect-unobservable`, held and observed again on the next pass. The token
decides WHICH of several concurrent writers acts. It does not replace the
owning-host rule, the recovery lock or the stamp re-read, which decide WHETHER
this recovery may act and all run before these functions are reached.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import claimed_by_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_RECOVERY,
    claim_blocked_write,
    claim_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
)
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
_NEEDS_HUMAN_REASON = "needs-human"
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


def release_claim_to_ready(*, repo: Path, work_item_id: str, run_id: str) -> str | None:
    """Return the item to `ready` with its `fabro` claim dropped.

    `None` when the transition landed, else the reason the claim is held.
    `run_id` is the run this recovery is recovering: a guarded transition lands
    only while the item is still `active`, assigned `fabro` and stamped with
    that run, which is `claim_unchanged` asked of the record the write is based
    on rather than of an earlier read.
    """
    refusal = attempt(
        action=lambda: claim_status_write(
            repo=repo,
            path=store_config(repo=repo),
            intent="absent-run-release",
            write=update_work_item_status,
            item_id=work_item_id,
            status=_READY_STATUS,
            clear_assignee=True,
            writer=WRITER_RECOVERY,
            still_as_decided=claimed_by_run(assignee=_FABRO_ASSIGNEE, run_id=run_id),
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return _hold_reason(refusal=refusal)


def rest_claim_for_a_human(*, repo: Path, work_item_id: str, run_id: str) -> str | None:
    """Rest the item at `blocked` / `needs-human` without changing admission.

    `None` when the transition landed, else the reason the claim is held.
    `run_id` binds a guarded rest to the claim exactly as it does the release.
    """
    refusal = attempt(
        action=lambda: claim_blocked_write(
            repo=repo,
            path=store_config(repo=repo),
            intent="absent-run-repeated-rest",
            write=update_work_item_blocked_state,
            item_id=work_item_id,
            blocked_reason=_NEEDS_HUMAN_REASON,
            writer=WRITER_RECOVERY,
            still_as_decided=claimed_by_run(assignee=_FABRO_ASSIGNEE, run_id=run_id),
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return _hold_reason(refusal=refusal)


def _hold_reason(*, refusal: AttemptFailure | str | None) -> str | None:
    """The hold a transition that did not land is reported under."""
    if refusal is None:
        return None
    return HOLD_CLAIM_CHANGED if refusal == HOLD_CLAIM_CHANGED else HOLD_EFFECT_UNOBSERVABLE

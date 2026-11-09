"""Performing one stale-assignee clearance: ordered effects, re-read before the last.

`SPECIFICATION/contracts.md` section "Stranded claim release" → "Stale assignee
clearance" says the clearance "follows 'Recovery is exclusive on its host and
convergent' above, with the assignee write in place of the status transition:
the journal record, then the ledger comment, then the assignee write last."
`_dispatcher_stranded_claim_recovery` owns that ordering for the claim routes;
this is the same ordering over a `ready` item, and it reuses that route's
fence, its replay readings and its row reads rather than restating them.

THE ASSIGNEE WRITE CHANGES NOTHING ELSE. Status, labels and the run stamp stay
as they are, so the write is the bare `clear_assignee` update and never a status
transition to `ready`: a transition into `ready` would restamp the item's
ready-dwell instant, moving the item in the ready queue for a change the clause
says leaves it unchanged. Under `dispatcher.claim_tokens` it is a claim-changing
write like any other and goes through the same guarded seam, bound to the
decision it rests on: still `ready`, still assigned `fabro`, still stamped with
this run.

EACH RE-READ REQUIRES THE ITEM TO BE STILL `ready`, still assigned `fabro`, and
stamped (not pending) with the same run. One that is not is `claim-changed`,
which is what lets a human valve that moved the item win over a clearance
already in flight. A read or write that fails is `effect-unobservable`, never
`claim-changed`: an unreadable row cannot support a positive finding about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    claimed_by_run,
    guarded_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    LEDGER_WRITE_ERRORS,
    WRITER_RECOVERY,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stale_assignee_records import (
    STALE_ASSIGNEE_CLEAR_STAGE,
    stale_assignee_comment_body,
    stale_assignee_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects import (
    claim_row,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_fence import (
    claim_recovery_fence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    HeldClaim,
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_replay import (
    EFFECT_WRITTEN,
    establish_comment,
    establish_journal_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "EFFECT_ASSIGNEE_CLEAR",
    "EFFECT_COMMENT",
    "EFFECT_JOURNAL_RECORD",
    "ROUTE_STALE_ASSIGNEE_CLEAR",
    "StaleClearRequest",
    "clear_stale_assignee",
]

ROUTE_STALE_ASSIGNEE_CLEAR = "stale-assignee-clear"
EFFECT_JOURNAL_RECORD = "journal-record"
EFFECT_COMMENT = "ledger-comment"
EFFECT_ASSIGNEE_CLEAR = "assignee-clear"

_READY_STATUS = "ready"
_FABRO_ASSIGNEE = "fabro"


@dataclass(frozen=True, kw_only=True)
class StaleClearRequest:
    """One graded stale assignee, with everything its clearance writes about it."""

    item: WorkItem
    run_id: str
    factory_name: str
    factory_server_url: str | None
    run_state: str


def clear_stale_assignee(
    *, repo: Path, journal: JournalFile, request: StaleClearRequest
) -> RecoveredClaim | HeldClaim:
    """Clear this stale assignee under the primary checkout's lock, in the clause's order."""
    with claim_recovery_fence(
        repo=repo, work_item_id=request.item.id, run_id=request.run_id
    ) as fenced:
        if not fenced:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        return _clear_fenced(repo=repo, journal=journal, request=request)


def _clear_fenced(
    *, repo: Path, journal: JournalFile, request: StaleClearRequest
) -> RecoveredClaim | HeldClaim:
    """The precondition read, the journal record, the comment, a last read, the write."""
    hold = _unchanged_hold(repo=repo, request=request)
    if hold is not None:
        return _held(request=request, reason=hold)
    item_id = request.item.id
    recorded = establish_journal_record(
        journal=journal,
        stage=STALE_ASSIGNEE_CLEAR_STAGE,
        work_item_id=item_id,
        run_id=request.run_id,
        record=stale_assignee_journal_record(
            work_item_id=item_id,
            run_id=request.run_id,
            factory_name=request.factory_name,
            factory_server_url=request.factory_server_url,
            run_state=request.run_state,
        ),
    )
    if recorded is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    commented = establish_comment(
        repo=repo,
        work_item_id=item_id,
        body=stale_assignee_comment_body(
            work_item_id=item_id,
            run_id=request.run_id,
            factory_name=request.factory_name,
            factory_server_url=request.factory_server_url,
            run_state=request.run_state,
        ),
    )
    if commented is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    # IMMEDIATELY before the assignee write, after both durable records.
    hold = _unchanged_hold(repo=repo, request=request)
    if hold is not None:
        return _held(request=request, reason=hold)
    refusal = write_assignee_clear(repo=repo, work_item_id=item_id, run_id=request.run_id)
    if refusal is not None:
        return _held(
            request=request,
            reason=HOLD_CLAIM_CHANGED
            if refusal == HOLD_CLAIM_CHANGED
            else HOLD_EFFECT_UNOBSERVABLE,
        )
    performed = tuple(
        effect
        for outcome, effect in ((recorded, EFFECT_JOURNAL_RECORD), (commented, EFFECT_COMMENT))
        if outcome == EFFECT_WRITTEN
    )
    return recovered(request=request, effects=(*performed, EFFECT_ASSIGNEE_CLEAR))


def write_assignee_clear(*, repo: Path, work_item_id: str, run_id: str) -> str | None:
    """Remove the `fabro` assignee and write nothing else; the hold reason if it did not land."""
    path = store_config(repo=repo)
    refusal = attempt(
        action=lambda: settle_claim_write(
            repo=repo,
            item_id=work_item_id,
            writer=WRITER_RECOVERY,
            intent=ROUTE_STALE_ASSIGNEE_CLEAR,
            unguarded=lambda: make_beads_client(config=path).update_issue(
                issue_id=work_item_id, clear_assignee=True
            ),
            guarded=lambda: guarded_write(
                path=path,
                item_id=work_item_id,
                writer=WRITER_RECOVERY,
                intent=ROUTE_STALE_ASSIGNEE_CLEAR,
                clear_assignee=True,
                still_as_decided=claimed_by_run(
                    assignee=_FABRO_ASSIGNEE, run_id=run_id, status=_READY_STATUS
                ),
            ),
        ),
        exceptions=LEDGER_WRITE_ERRORS,
    )
    return HOLD_EFFECT_UNOBSERVABLE if isinstance(refusal, AttemptFailure) else refusal


def recovered(*, request: StaleClearRequest, effects: tuple[str, ...]) -> RecoveredClaim:
    """The report of a clearance: the run state is its reason, the status unchanged."""
    return RecoveredClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        reason=request.run_state,
        route=ROUTE_STALE_ASSIGNEE_CLEAR,
        status=_READY_STATUS,
        effects_written=effects,
    )


def _unchanged_hold(*, repo: Path, request: StaleClearRequest) -> str | None:
    """The hold the item's current row earns, or None while it is still the stale assignee."""
    row = claim_row(repo=repo, work_item_id=request.item.id)
    if row is None:
        return HOLD_EFFECT_UNOBSERVABLE
    return None if _still_stale(row=row, run_id=request.run_id) else HOLD_CLAIM_CHANGED


def _still_stale(*, row: ClaimRow, run_id: str) -> bool:
    """Still `ready`, still assigned `fabro`, and stamped (not pending) with this run."""
    if row.status != _READY_STATUS or row.assignee != _FABRO_ASSIGNEE:
        return False
    stamp = row.stamp
    return stamp is not None and not stamp.pending and stamp.run_id == run_id


def _held(*, request: StaleClearRequest, reason: str) -> HeldClaim:
    return HeldClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        dispatching_host=None,
        hold_reason=reason,
        remedy=None,
    )

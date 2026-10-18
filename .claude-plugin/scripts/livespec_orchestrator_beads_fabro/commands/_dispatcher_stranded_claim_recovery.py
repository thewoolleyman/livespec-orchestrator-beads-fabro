"""Performing one claim recovery: ordered effects, and a re-read before each.

BOTH ABSENT-RUN ROUTES TRAVEL ONE SEQUENCE. The release returns the item to
`ready` and the repeat rests it at `blocked / needs-human`, and they differ in
exactly three values — the journal stage, the recorded reason, and the status
the transition writes. `_route` resolves those three in one place, so the
ordering guarantee below is asserted once for both rather than implemented
twice.

THE ORDER IS THE CONTRACT'S. The journal record first, then the ledger
comment, then the status transition LAST, so the item becomes dispatchable only
after its audit trail exists. An operator who finds a `ready` item can always
find the record and the comment that released it; the reverse order would make
"released with no account" a reachable state, and a ledger comment can be
neither edited nor deleted afterwards.

RE-READ LAST. Immediately before the transition — after the record and the
comment — the stamp is read again, and the transition is written only if the
item is still `active`, still assigned `fabro`, and still stamped with the run
this recovery is recovering. Anything else is `claim-changed` and the
transition is not written. That is what makes a human valve, or an admission
that followed one, win over a recovery already in flight. The residual window
between that read and the write is ratified as parity with the Dispatcher's own
terminal path (coordinator ruling R144); closing it needs a server-enforced
claim generation, which work-item `bd-ib-jjws2` tracks.

A LEDGER READ THAT FAILS IS `effect-unobservable`, not `claim-changed`. The
fourteen reasons name no "the re-read itself failed" condition, and the two
candidate readings are not interchangeable: `claim-changed` asserts a positive
finding about the row, which an unreadable row cannot support. Reporting the
failure to measure is both honest and fail-closed — nothing is written either
way, and the next pass takes the reading again.

THE LEDGER WRITES DELIBERATELY DO NOT GO THROUGH THE RECONCILER'S OWN SEAM.
`_dispatcher_reconcile_runs_inputs` hands the RUN lane a comments-only ledger
surface, precisely so that reconciling a run structurally cannot change an
item's status. That guarantee still holds and must keep holding: the status
changes this module writes are the three the clause's "Status changes" bullet
enumerates, they belong to the CLAIM lane, and they are written here through
the same store seams the pre-run and stall releases use — never by widening
the run lane's seam, which would make the run lane's structural guarantee a
convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_ABSENT_RUN_RELEASE,
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    REASON_RUN_ABSENT,
    REASON_RUN_ABSENT_REPEATED,
    STRANDED_CLAIM_RELEASE_STAGE,
    STRANDED_CLAIM_REPEATED_STAGE,
    HeldClaim,
    RecoveredClaim,
    recovery_journal_record,
    release_comment_body,
    repeated_comment_body,
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
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "EFFECT_COMMENT",
    "EFFECT_JOURNAL_RECORD",
    "EFFECT_TRANSITION",
    "ClaimRecoveryRequest",
    "recover_claim",
]

EFFECT_JOURNAL_RECORD = "journal-record"
EFFECT_COMMENT = "ledger-comment"
EFFECT_TRANSITION = "status-transition"

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


@dataclass(frozen=True, kw_only=True)
class ClaimRecoveryRequest:
    """One graded claim, with everything its recovery writes about it."""

    item: WorkItem
    run_id: str
    factory_name: str
    factory_server_url: str | None
    action: str
    # The run of the dispatch BEFORE this claim's, which only the repeat route
    # renders: its comment has to NAME both runs, because the pair is the
    # finding and an operator reading the newer run alone cannot see it. It is
    # optional because the predecessor may have recorded no run id, which the
    # comment states rather than omitting.
    predecessor_run_id: str | None = None


def recover_claim(
    *,
    repo: Path,
    journal: JournalFile,
    request: ClaimRecoveryRequest,
) -> RecoveredClaim | HeldClaim:
    """Release this claim, writing its three effects in the clause's order.

    The PRECONDITION read is kept apart from the writes below it so that the
    one thing a reader has to check — that nothing is written before the row
    has been re-read and found unchanged — is visible without following the
    effect sequence.
    """
    row = _claim_row(repo=repo, work_item_id=request.item.id)
    if row is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    if not _claim_unchanged(row=row, run_id=request.run_id):
        return _held(request=request, reason=HOLD_CLAIM_CHANGED)
    return _write_release_effects(repo=repo, journal=journal, request=request)


def _write_release_effects(
    *,
    repo: Path,
    journal: JournalFile,
    request: ClaimRecoveryRequest,
) -> RecoveredClaim | HeldClaim:
    """The journal record, the ledger comment, and the transition, in that order.

    BOTH absent-run routes travel this one sequence, differing only in the
    three values `_route` resolves: a second writer for the repeat arm would be
    a second ordering of the same three effects, and the ordering is the
    guarantee.
    """
    journal.append(
        record=recovery_journal_record(
            stage=_route(request=request).stage,
            recovered=_recovered(request=request, effects=()),
        )
    )
    if not _append_comment(repo=repo, request=request):
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    # IMMEDIATELY before the transition, after both durable records: the one
    # re-read the clause names, and the only one whose failure withholds the
    # status write.
    final = _claim_row(repo=repo, work_item_id=request.item.id)
    if final is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    if not _claim_unchanged(row=final, run_id=request.run_id):
        return _held(request=request, reason=HOLD_CLAIM_CHANGED)
    if not _transition(repo=repo, request=request):
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    return _recovered(
        request=request,
        effects=(EFFECT_JOURNAL_RECORD, EFFECT_COMMENT, EFFECT_TRANSITION),
    )


@dataclass(frozen=True, kw_only=True)
class _Route:
    """What distinguishes the two absent-run routes: a stage, a reason, a rest."""

    stage: str
    reason: str
    status: str


def _route(*, request: ClaimRecoveryRequest) -> _Route:
    if request.action == ACTION_ABSENT_RUN_RELEASE:
        return _Route(
            stage=STRANDED_CLAIM_RELEASE_STAGE,
            reason=REASON_RUN_ABSENT,
            status=_READY_STATUS,
        )
    return _Route(
        stage=STRANDED_CLAIM_REPEATED_STAGE,
        reason=REASON_RUN_ABSENT_REPEATED,
        status=_BLOCKED_STATUS,
    )


def _comment_body(*, request: ClaimRecoveryRequest) -> str:
    if request.action == ACTION_ABSENT_RUN_RELEASE:
        return release_comment_body(
            work_item_id=request.item.id,
            run_id=request.run_id,
            factory_name=request.factory_name,
            factory_server_url=request.factory_server_url,
        )
    return repeated_comment_body(
        work_item_id=request.item.id,
        run_id=request.run_id,
        predecessor_run_id=request.predecessor_run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
    )


def _append_comment(*, repo: Path, request: ClaimRecoveryRequest) -> bool:
    written = attempt(
        action=lambda: append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=request.item.id,
            body=_comment_body(request=request),
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return not isinstance(written, AttemptFailure)


def _transition(*, repo: Path, request: ClaimRecoveryRequest) -> bool:
    """`ready` with the claim dropped, or the `needs-human` rest of a repeat.

    The release goes through the SAME seam the pre-run and stall releases use —
    `status="ready"` with `clear_assignee=True` — so a released stranded claim
    leaves the ledger in one shape rather than a third that merely looks like
    the other two. The repeat goes through the escalation seam, which REPLACES
    the blocked-reason label rather than adding one beside it, and sets
    `admission:manual` so nothing automatic leaves that state.
    """
    if request.action != ACTION_ABSENT_RUN_RELEASE:
        rested = attempt(
            action=lambda: update_work_item_blocked_state(
                path=store_config(repo=repo),
                item_id=request.item.id,
                status=_BLOCKED_STATUS,
                blocked_reason=_NEEDS_HUMAN_REASON,
                admission_policy=_MANUAL_ADMISSION,
            ),
            exceptions=_LEDGER_ERRORS,
        )
        return not isinstance(rested, AttemptFailure)
    applied = attempt(
        action=lambda: update_work_item_status(
            path=store_config(repo=repo),
            item_id=request.item.id,
            status=_READY_STATUS,
            clear_assignee=True,
        ),
        exceptions=_LEDGER_ERRORS,
    )
    return not isinstance(applied, AttemptFailure)


def _claim_row(*, repo: Path, work_item_id: str) -> ClaimRow | None:
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=work_item_id),
        exceptions=_LEDGER_ERRORS,
    )
    return None if isinstance(row, AttemptFailure) else row


def _claim_unchanged(*, row: ClaimRow, run_id: str) -> bool:
    if row.status != _ACTIVE_STATUS or row.assignee != _FABRO_ASSIGNEE:
        return False
    stamp = row.stamp
    return stamp is not None and not stamp.pending and stamp.run_id == run_id


def _recovered(*, request: ClaimRecoveryRequest, effects: tuple[str, ...]) -> RecoveredClaim:
    route = _route(request=request)
    return RecoveredClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        reason=route.reason,
        route=request.action,
        status=route.status,
        effects_written=effects,
    )


def _held(*, request: ClaimRecoveryRequest, reason: str) -> HeldClaim:
    return HeldClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        dispatching_host=None,
        hold_reason=reason,
        remedy=None,
    )

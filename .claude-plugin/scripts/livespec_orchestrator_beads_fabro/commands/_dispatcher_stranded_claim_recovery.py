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

THE FOUR LEDGER ACTS LIVE IN `_dispatcher_stranded_claim_effects`, so this
module is the ORDER and that one is what the order is over. None of them
raises: a recovery runs inside a pass that must not die on one unreachable
tenant, and every failure there means the same thing here — the effect could
not be established, so nothing further is written.

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

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects import (
    claim_row,
    claim_unchanged,
    release_claim_to_ready,
    rest_claim_for_a_human,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_fence import (
    claim_recovery_fence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_ABSENT_RUN_RELEASE,
    ACTION_TERMINAL_COMPLETION,
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    REASON_RUN_ABSENT,
    REASON_RUN_ABSENT_REPEATED,
    STRANDED_CLAIM_RELEASE_STAGE,
    STRANDED_CLAIM_REPEATED_STAGE,
    STRANDED_CLAIM_TERMINAL_STAGE,
    HeldClaim,
    RecoveredClaim,
    recovery_journal_record,
    release_comment_body,
    repeated_comment_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_replay import (
    EFFECT_WRITTEN,
    establish_comment,
    establish_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal import (
    TerminalObservation,
    apply_terminal_disposition,
)
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
_READY_STATUS = "ready"
_BLOCKED_STATUS = "blocked"


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
    # The already-OBSERVED terminal reading, carried rather than re-taken: the
    # grading needed it to decide whether the failure evidence was readable at
    # all, and a second `fabro inspect` here could answer about a record the
    # first reading already judged.
    terminal: TerminalObservation | None = None


def recover_claim(
    *,
    repo: Path,
    journal: JournalFile,
    request: ClaimRecoveryRequest,
    now_iso: str,
) -> RecoveredClaim | HeldClaim:
    """Release this claim under the primary checkout's lock, in the clause's order.

    The FENCE is outermost, so every path below it — each hold, each convergent
    skip, and the terminal delegation that reaches the Dispatcher's own
    dispositions — drops the lock on the way out.
    """
    with claim_recovery_fence(
        repo=repo, work_item_id=request.item.id, run_id=request.run_id
    ) as fenced:
        if not fenced:
            return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
        return _recover_fenced(repo=repo, journal=journal, request=request, now_iso=now_iso)


def _recover_fenced(
    *,
    repo: Path,
    journal: JournalFile,
    request: ClaimRecoveryRequest,
    now_iso: str,
) -> RecoveredClaim | HeldClaim:
    """One recovery, with the exclusion already held.

    The PRECONDITION read is kept apart from the writes below it so that the
    one thing a reader has to check — that nothing is written before the row
    has been re-read and found unchanged — is visible without following the
    effect sequence.
    """
    row = claim_row(repo=repo, work_item_id=request.item.id)
    if row is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    if not claim_unchanged(row=row, run_id=request.run_id):
        return _held(request=request, reason=HOLD_CLAIM_CHANGED)
    if request.action == ACTION_TERMINAL_COMPLETION:
        return _complete_terminal(repo=repo, journal=journal, request=request, now_iso=now_iso)
    return _write_release_effects(repo=repo, journal=journal, request=request)


def _complete_terminal(
    *,
    repo: Path,
    journal: JournalFile,
    request: ClaimRecoveryRequest,
    now_iso: str,
) -> RecoveredClaim | HeldClaim:
    """Hand a terminal run to the Dispatcher's own disposition.

    The announcement row is written BEFORE the dispositions, which is the
    opposite order from the absent-run route and is deliberate: the
    dispositions are DELEGATED and each owns its own records, so the row saying
    reconciliation finished what a dead Dispatcher left undone has to exist
    before control leaves this module. It restates no disposition it did not
    decide, which is why it carries the observed terminal STATUS as its reason
    rather than a route name of its own.
    """
    terminal = request.terminal
    if terminal is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    journal.append(
        record=recovery_journal_record(
            stage=STRANDED_CLAIM_TERMINAL_STAGE,
            recovered=_terminal_recovered(request=request, terminal=terminal, effects=()),
        )
    )
    applied = apply_terminal_disposition(
        repo=repo,
        item=request.item,
        observation=terminal,
        journal=journal,
        now_iso=now_iso,
    )
    return _terminal_recovered(
        request=request, terminal=terminal, effects=(EFFECT_JOURNAL_RECORD, *applied)
    )


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

    EACH DURABLE EFFECT IS SKIPPED IF IT ALREADY LANDED, which is what makes an
    interrupted recovery converge rather than duplicate. The skips do not relax
    the ORDER: a replay still establishes the record, then the comment, then
    re-reads and transitions, and the effects it reports are the ones it
    actually performed.
    """
    stage = _route(request=request).stage
    recorded = establish_journal_record(
        journal=journal,
        stage=stage,
        work_item_id=request.item.id,
        run_id=request.run_id,
        record=recovery_journal_record(
            stage=stage, recovered=_recovered(request=request, effects=())
        ),
    )
    if recorded is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    commented = establish_comment(
        repo=repo, work_item_id=request.item.id, body=_comment_body(request=request)
    )
    if commented is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    # IMMEDIATELY before the transition, after both durable records: the one
    # re-read the clause names, and the only one whose failure withholds the
    # status write.
    final = claim_row(repo=repo, work_item_id=request.item.id)
    if final is None:
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    if not claim_unchanged(row=final, run_id=request.run_id):
        return _held(request=request, reason=HOLD_CLAIM_CHANGED)
    if not _transition(repo=repo, request=request):
        return _held(request=request, reason=HOLD_EFFECT_UNOBSERVABLE)
    return _recovered(
        request=request,
        effects=(
            *_performed(outcome=recorded, effect=EFFECT_JOURNAL_RECORD),
            *_performed(outcome=commented, effect=EFFECT_COMMENT),
            EFFECT_TRANSITION,
        ),
    )


def _performed(*, outcome: str, effect: str) -> tuple[str, ...]:
    """The effect name, or nothing when this pass found it already written."""
    return (effect,) if outcome == EFFECT_WRITTEN else ()


@dataclass(frozen=True, kw_only=True)
class _Route:
    """What distinguishes the two absent-run routes: a stage, a reason, a rest."""

    stage: str
    reason: str
    status: str


def _route(*, request: ClaimRecoveryRequest) -> _Route:
    """Which of the TWO absent-run routes this request is.

    Reached only for those two: the terminal completion renders its own record
    through `_terminal_recovered`, because its reason is the observed terminal
    status rather than a route name this module chose.
    """
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


def _transition(*, repo: Path, request: ClaimRecoveryRequest) -> bool:
    """The status write each absent-run route owes, through its shared seam."""
    if request.action == ACTION_ABSENT_RUN_RELEASE:
        return release_claim_to_ready(repo=repo, work_item_id=request.item.id)
    return rest_claim_for_a_human(repo=repo, work_item_id=request.item.id)


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


def _terminal_recovered(
    *,
    request: ClaimRecoveryRequest,
    terminal: TerminalObservation,
    effects: tuple[str, ...],
) -> RecoveredClaim:
    """The record a terminal completion leaves.

    It carries the OBSERVED terminal status as its reason and reports the item
    as it stands, because this route decides no disposition: whichever route
    the Dispatcher's own handling took has already written its own account of
    where the item went, and restating it here would be a second account of
    one event.
    """
    return RecoveredClaim(
        work_item_id=request.item.id,
        run_id=request.run_id,
        factory_name=request.factory_name,
        factory_server_url=request.factory_server_url,
        reason=terminal.outcome.status,
        route=request.action,
        status=_ACTIVE_STATUS,
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

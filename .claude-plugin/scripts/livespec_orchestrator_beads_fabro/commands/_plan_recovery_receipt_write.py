"""Recording one causal recovery attempt's receipts as an authority transition.

A receipt is a FACT ABOUT THE PLAN'S AUTHORITY, so it moves through the same
epoch-token chain every sanctioned plan write does and never through a direct
metadata write. `next_action` and the epic's metadata are PROJECTIONS of
committed transitions; a receipt written straight onto either would be a claim
about execution that no serialized transition stands behind, and the two readings
would then disagree with nothing to say which was right. The exclusion is the
Beads server's conditional close inside `_plan_epoch_chain` — nothing here
acquires a lock, opens a socket or touches a host directory, because writers may
run on hosts that share nothing but that server
(`.ai/ledger-writers-are-multi-host.md`, maintainer ruling 2026-10-12).

THE ATTEMPT IS MATCHED BY ITS OWN ID, AND A SUPERSEDED ATTEMPT IS REFUSED RATHER
THAN RE-TARGETED. A receipt is evidence about ONE authorized operation. Attaching
one to whatever attempt happens to be current would credit a later attempt with
an earlier attempt's dispatch, and the result reads exactly like a correct
receipt.

THIS WRITE PROJECTS NO POINTER AND APPENDS NO HANDOFF. Recording an observation
of work that already happened accepts no handoff and grants no time, so the
committed authority carries the SAME obligation it observed — which is the one
property `contracts.md` puts beyond every writer's reach: "Its attempt budget
MUST NOT replace or postpone the original obligation deadline."
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    COMMITTED,
    ChainHead,
    StaleEpochRefusal,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipts import (
    EVENT_RECEIPT,
    RECEIPTS_RECORDED,
    RECORDED_NOT_EXECUTED,
    ReceiptRefusal,
    ReceiptSet,
    RecordedAttempt,
    dispatched_subject,
    execution_records,
    receipt_set,
    receipted_attempt,
    recorded_attempt,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "RecoveryReceiptRequest",
    "RecoveryReceiptWrite",
    "receipt_operation_id",
    "record_impl_recovery_receipts",
    "record_recovery_receipts",
]


@dataclass(frozen=True, kw_only=True)
class RecoveryReceiptRequest:
    """One receipt-recording pass over one plan epic's recorded attempt.

    `attempt_id` is the attempt the caller believes it is receipting, and it is
    REQUIRED: a pass that receipted whatever attempt was current would need no
    such field, which is exactly the re-targeting this write refuses.
    `journal_path` is the dispatch journal the executor wrote; `None` is a
    repository that has never dispatched.
    """

    config: StoreConfig
    epic_id: str
    attempt_id: str
    journal_path: Path | None
    author: str
    now: str
    operation_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecoveryReceiptWrite:
    """What one receipt-recording pass observed and committed.

    `status` is what says whether a transition happened at all, and `idempotent`
    only distinguishes a fresh commit from a recovered retry WITHIN the recorded
    status. A `recorded-but-not-executed` pass committed nothing, so it reports
    `idempotent=False` and the epoch it observed: there is nothing for a retry to
    recover, because there was nothing to record.
    """

    attempt_id: str
    receipts: ReceiptSet
    status: str
    epoch: int
    idempotent: bool


def receipt_operation_id(*, request: RecoveryReceiptRequest, receipts: ReceiptSet) -> str:
    """A deterministic operation identity for one observation of one attempt.

    THE RECEIPTS THEMSELVES ARE PART OF THE IDENTITY. A re-read of the same
    journal is the SAME logical operation and must recover its original
    transition rather than burn an epoch and append a second progress event; a
    read that found MORE evidence — a run id where there had been only a dispatch
    id — is a different observation and must commit its own transition.
    """
    material = "\x1f".join(
        (
            request.epic_id,
            request.attempt_id,
            receipts.claim or "",
            receipts.execution or "",
            receipts.outcome or "",
        )
    )
    return f"plan-receipt-{sha256(material.encode('utf-8')).hexdigest()[:16]}"


def record_recovery_receipts(
    *,
    request: RecoveryReceiptRequest,
) -> RecoveryReceiptWrite | ReceiptRefusal:
    """Record what the executor's own records say one recorded attempt did."""
    head = read_chain_head(config=request.config, epic_id=request.epic_id)
    if isinstance(head, ChainFinding):
        return ReceiptRefusal(detail=f"{head.code}: {head.detail} — {head.remedy}")
    recorded = recorded_attempt(authority_record=head.authority.last_recovery_attempt)
    if recorded is None:
        return ReceiptRefusal(
            detail=(
                f"{request.epic_id} records no readable causal recovery attempt, so there"
                " is no attempt to receipt"
            )
        )
    if recorded.attempt_id != request.attempt_id:
        return ReceiptRefusal(
            detail=(
                f"attempt {request.attempt_id} is no longer the recorded attempt of"
                f" {request.epic_id}, which stands at {recorded.attempt_id}; a receipt is"
                " evidence about ONE authorized operation, so it is refused rather than"
                " attached to the newer attempt"
            )
        )
    receipts = _observed_receipts(request=request, recorded=recorded)
    if receipts == ReceiptSet():
        return RecoveryReceiptWrite(
            attempt_id=recorded.attempt_id,
            receipts=receipts,
            status=RECORDED_NOT_EXECUTED,
            epoch=head.epoch,
            idempotent=False,
        )
    return _commit(request=request, head=head, recorded=recorded, receipts=receipts)


def record_impl_recovery_receipts(
    *,
    config: StoreConfig,
    work_item_id: str,
    journal_path: Path | None,
    author: str,
    now: str,
) -> tuple[RecoveryReceiptWrite | ReceiptRefusal, ...]:
    """Receipt every CURRENT recovery attempt that authorized this impl action.

    The drive executor names a work item, not a plan epic or an attempt.  The
    chain is therefore surveyed at execution time to find the only attempts
    whose recorded operation authorizes that item.  Each candidate carries its
    own attempt id back into `record_recovery_receipts`, which re-reads and
    rejects a superseded attempt instead of attaching the evidence to a newer
    one.  There is no local coordination: the Beads conditional close remains
    the multi-host serialization boundary.
    """
    operation = f"impl:{work_item_id}"
    return tuple(
        record_recovery_receipts(
            request=RecoveryReceiptRequest(
                config=config,
                epic_id=epic_id,
                attempt_id=attempt_id,
                journal_path=journal_path,
                author=author,
                now=now,
            )
        )
        for epic_id, attempt_id in _matching_impl_attempts(config=config, operation=operation)
    )


def _matching_impl_attempts(*, config: StoreConfig, operation: str) -> tuple[tuple[str, str], ...]:
    """The current plan attempts that authorize exactly one impl operation."""
    client = make_beads_client(config=config)
    return tuple(
        (epic_id, attempt.attempt_id)
        for issue in client.list_issues()
        for epic_id in (str(issue["id"]),)
        for head in (read_chain_head(config=config, epic_id=epic_id),)
        if isinstance(head, ChainHead)
        for attempt in (recorded_attempt(authority_record=head.authority.last_recovery_attempt),)
        if attempt is not None and attempt.next_operation == operation
    )


def _observed_receipts(
    *,
    request: RecoveryReceiptRequest,
    recorded: RecordedAttempt,
) -> ReceiptSet:
    """The receipts this attempt's own authorized operation left behind.

    An operation that dispatches NOTHING short-circuits before the journal is
    read at all, rather than reading it and finding nothing: the two states have
    the same receipts and different meanings, and a read-only diagnosis sharing a
    journal with every other dispatched item would otherwise be one match away
    from being credited with another item's work.
    """
    subject = dispatched_subject(next_operation=recorded.next_operation)
    if subject is None:
        return ReceiptSet()
    return receipt_set(
        records=execution_records(
            records=journal_records(journal_path=request.journal_path),
            work_item_id=subject,
        )
    )


def _commit(
    *,
    request: RecoveryReceiptRequest,
    head: ChainHead,
    recorded: RecordedAttempt,
    receipts: ReceiptSet,
) -> RecoveryReceiptWrite | ReceiptRefusal:
    """Commit the observation as one authority transition, or report why not."""
    operation_id = request.operation_id or receipt_operation_id(request=request, receipts=receipts)
    committed = commit_transition(
        config=request.config,
        epic_id=request.epic_id,
        request=TransitionRequest(
            operation_id=operation_id,
            observed_head=head,
            authority=_receipted_authority(head=head, recorded=recorded, receipts=receipts),
            event_kind=EVENT_RECEIPT,
            author=request.author,
            now=request.now,
        ),
    )
    if isinstance(committed, StaleEpochRefusal):
        return ReceiptRefusal(
            detail=(
                f"a concurrent writer committed from epoch {committed.observed_epoch};"
                f" re-read the plan and retry: {committed.detail}"
            )
        )
    if isinstance(committed, ChainFinding):
        return ReceiptRefusal(detail=f"{committed.code}: {committed.detail}")
    return RecoveryReceiptWrite(
        attempt_id=recorded.attempt_id,
        receipts=receipts,
        status=RECEIPTS_RECORDED,
        epoch=committed.payload.new_epoch,
        idempotent=committed.source != COMMITTED,
    )


def _receipted_authority(
    *,
    head: ChainHead,
    recorded: RecordedAttempt,
    receipts: ReceiptSet,
) -> AuthorityState:
    """The observed authority with ONLY the attempt's three receipts moved.

    Every obligation field is carried from the OBSERVED authority rather than
    recomputed or defaulted away: `contracts.md` puts the deadline and the
    handoff ceiling beyond every writer's reach, and a receipt writer is a writer
    like any other. The receipt ring is deliberately absent, because the chain
    itself supplies it — a writer's own ring would erase the receipts that make
    another operation's retry recognisable.
    """
    return AuthorityState(
        required_result=head.authority.required_result,
        original_deadline=head.authority.original_deadline,
        max_handoffs=head.authority.max_handoffs,
        consumed_handoffs=head.authority.consumed_handoffs,
        last_recovery_attempt=receipted_attempt(recorded=recorded, receipts=receipts),
    )

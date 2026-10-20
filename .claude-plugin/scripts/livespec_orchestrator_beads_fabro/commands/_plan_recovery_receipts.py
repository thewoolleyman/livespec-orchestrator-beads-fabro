"""What an executed causal recovery attempt's own executor recorded about it.

PURE. `contracts.md` section "Required result, budget and progress epoch" fixes
the rule this module serves the second half of: "A fresh event authorizes one
recovery attempt; recording it is not evidence that the command executed or that
the target was fulfilled. Claim, execution and outcome receipts MUST remain
distinct." `_plan_recovery` holds the FIRST half — a fresh attempt asserting any
receipt is refused — and this is the half that fills them in afterwards, from the
records the executor itself left behind.

EVERY RECEIPT IS DERIVED FROM A DURABLE EXECUTOR RECORD, AND THERE IS
DELIBERATELY NO PARAMETER A CALLER CAN PUT ONE IN. A receipt a caller could WRITE
is a receipt a caller could INVENT, which would reduce the whole distinction to a
naming convention: the point of three separate receipts is that each is evidence
a DIFFERENT observer took. So the claim comes from the dispatch journal's
`dispatch-id` record, the execution from the newest Fabro run id that journal
names for the same item, and the outcome from the terminal dispatch outcome it
records.

THE SUBJECT IS DERIVED FROM THE RECORDED ATTEMPT AND IS NOT SUPPLIED EITHER. The
attempt's own `next_operation` names the work-item its authorized operation
dispatches, so a caller cannot point one attempt's receipts at another item's
journal records — and every leg below matches on that subject, because a dispatch
journal is shared by every item a repository has ever dispatched.

AN OPERATION THAT DISPATCHES NOTHING IS `recorded but not executed` RATHER THAN
AN ATTEMPT WHOSE RECEIPTS WENT MISSING. Only `impl:<item>` dispatches work: the
plan-progress diagnosis is read-only by contract and the four spec operations run
through the Livespec Driver, so neither produces a dispatch id, a factory run or a
terminal outcome. Reporting those as an executed attempt with unreadable receipts
would send an operator hunting a journal record that was never going to exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_recovery import is_executable_operation
from livespec_orchestrator_beads_fabro.commands._run_attribution import newest_journaled_run_id

__all__: list[str] = [
    "EVENT_RECEIPT",
    "RECEIPTS_RECORDED",
    "RECORDED_NOT_EXECUTED",
    "ExecutionRecords",
    "ReceiptRefusal",
    "ReceiptSet",
    "RecordedAttempt",
    "dispatched_subject",
    "execution_records",
    "receipt_set",
    "receipted_attempt",
    "recorded_attempt",
]

# The event kind a receipt transition commits. It is named HERE rather than beside
# `_plan_progress_decision`'s four kinds because that module enumerates exactly
# the kinds its own decision ladder returns, and a receipt is not one of its
# decisions: it observes work that already happened rather than deciding what a
# write may do to the obligation.
EVENT_RECEIPT = "receipt"

# What one receipt-recording pass did. The two are kept apart because they call
# for opposite follow-ups: a recorded receipt is durable evidence an operator can
# read, while a recorded-but-not-executed attempt means the authorized operation
# has still not run and the bound is still being spent.
RECEIPTS_RECORDED = "receipts-recorded"
RECORDED_NOT_EXECUTED = "recorded-but-not-executed"

# The dispatch journal stages each receipt is read from. Re-spelled here rather
# than imported, because the modules that emit them are dispatcher-side and a
# plan-side import of one would couple the plan authority to the engine.
_DISPATCH_ID_STAGE = "dispatch-id"
_OUTCOME_STAGE = "outcome"
_STAGE_FIELD = "stage"
_WORK_ITEM_FIELD = "work_item_id"
_DISPATCH_ID_FIELD = "dispatch_id"
_OUTCOME_FIELD = "outcome"
_STATUS_FIELD = "status"
_PR_NUMBER_FIELD = "pr_number"

# The attempt object's own field names, as `_plan_recovery.recovery_record`
# renders them. `_plan_progress_resume` re-spells the same names for the same
# reason: they are private to their owning module and a cross-module private
# import is refused.
_ATTEMPT_FIELD = "attempt"
_ATTEMPT_ID_FIELD = "attempt_id"
_NEXT_OPERATION_FIELD = "next_operation"
_CLAIM_RECEIPT_FIELD = "claim_receipt"
_EXECUTION_RECEIPT_FIELD = "execution_receipt"
_OUTCOME_RECEIPT_FIELD = "outcome_receipt"

_IMPL_OPERATION_PREFIX = "impl:"


@dataclass(frozen=True, kw_only=True)
class ExecutionRecords:
    """What the dispatch journal records about one work-item's newest dispatch."""

    dispatch_id: str | None = None
    run_id: str | None = None
    outcome_status: str | None = None
    outcome_stage: str | None = None
    pr_number: int | None = None


@dataclass(frozen=True, kw_only=True)
class ReceiptSet:
    """The three distinct receipts, each `None` until its own evidence exists."""

    claim: str | None = None
    execution: str | None = None
    outcome: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecordedAttempt:
    """The attempt an epic's authority records, as a receipt writer reads it.

    `record` is the whole `last_recovery_attempt` object and `attempt` is its
    `attempt` sub-object. BOTH are carried verbatim rather than reduced to the
    named fields above, because a rewrite that rebuilt either from named fields
    would be one edit away from dropping a key it had not been told about — and
    the item-attributable repetition count lives in the outer object.
    """

    attempt_id: str
    next_operation: str
    receipts: ReceiptSet
    record: Mapping[str, Any]
    attempt: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class ReceiptRefusal:
    """Why one receipt was not recorded on the attempt it named."""

    detail: str


def dispatched_subject(*, next_operation: str) -> str | None:
    """The work-item one attempt's operation dispatches, or `None` when none is.

    The operation is re-checked against the closed grammar rather than trusted,
    because it is read back out of ledger data and a stored string is not
    evidence that it was ever validated.
    """
    if not is_executable_operation(operation=next_operation):
        return None
    if not next_operation.startswith(_IMPL_OPERATION_PREFIX):
        return None
    return next_operation.removeprefix(_IMPL_OPERATION_PREFIX)


def execution_records(
    *,
    records: Iterable[Mapping[str, object]],
    work_item_id: str,
) -> ExecutionRecords:
    """Read what the dispatch journal records about one work-item's dispatches.

    LAST-WINS over file order, which is sound because the journal is append-only:
    a later record for the same item cannot describe an earlier dispatch. The run
    id comes from `newest_journaled_run_id` rather than a scan written here, so
    the run this takes a receipt for is exactly the run every other consumer
    calls this item's newest.
    """
    ordered = tuple(records)
    dispatch_ids = tuple(
        found
        for record in ordered
        if record.get(_STAGE_FIELD) == _DISPATCH_ID_STAGE
        and record.get(_WORK_ITEM_FIELD) == work_item_id
        and (found := _text(value=record.get(_DISPATCH_ID_FIELD))) is not None
    )
    outcomes = tuple(
        found
        for record in ordered
        if (found := _outcome_object(record=record, work_item_id=work_item_id)) is not None
    )
    outcome = outcomes[-1] if outcomes else {}
    return ExecutionRecords(
        dispatch_id=dispatch_ids[-1] if dispatch_ids else None,
        run_id=newest_journaled_run_id(records=ordered, work_item_id=work_item_id),
        outcome_status=_text(value=outcome.get(_STATUS_FIELD)),
        outcome_stage=_text(value=outcome.get(_STAGE_FIELD)),
        pr_number=_pr_number(value=outcome.get(_PR_NUMBER_FIELD)),
    )


def receipt_set(*, records: ExecutionRecords) -> ReceiptSet:
    """Render each durable executor record as the receipt it is evidence for.

    Each receipt NAMES the record it was read from rather than carrying its bare
    identifier, because the three sit side by side on one attempt and an operator
    reading them has to be able to tell which observer took which — a bare id
    says nothing about whether it is a dispatch, a run or a terminal.
    """
    return ReceiptSet(
        claim=None if records.dispatch_id is None else f"dispatch {records.dispatch_id}",
        execution=None if records.run_id is None else f"fabro run {records.run_id}",
        outcome=_outcome_receipt(records=records),
    )


def recorded_attempt(*, authority_record: object) -> RecordedAttempt | None:
    """The attempt an authority records, or `None` when none is readable.

    Fails CLOSED on every partial read, for the same reason
    `_plan_progress_resume`'s bounded-attempt read does: the id read here is what
    a receipt is MATCHED against, so a half-read record would let a receipt land
    on an attempt nobody could identify — which is indistinguishable at every
    surface from a receipt that was matched correctly.
    """
    if not isinstance(authority_record, dict):
        return None
    record = cast("dict[str, Any]", authority_record)
    attempt = record.get(_ATTEMPT_FIELD)
    if not isinstance(attempt, dict):
        return None
    fields = cast("dict[str, Any]", attempt)
    attempt_id = _text(value=fields.get(_ATTEMPT_ID_FIELD))
    operation = _text(value=fields.get(_NEXT_OPERATION_FIELD))
    if attempt_id is None or operation is None:
        return None
    return RecordedAttempt(
        attempt_id=attempt_id,
        next_operation=operation,
        receipts=ReceiptSet(
            claim=_text(value=fields.get(_CLAIM_RECEIPT_FIELD)),
            execution=_text(value=fields.get(_EXECUTION_RECEIPT_FIELD)),
            outcome=_text(value=fields.get(_OUTCOME_RECEIPT_FIELD)),
        ),
        record=record,
        attempt=fields,
    )


def receipted_attempt(
    *,
    recorded: RecordedAttempt,
    receipts: ReceiptSet,
) -> dict[str, Any]:
    """The `last_recovery_attempt` record with the three receipts filled in.

    Both objects are SPREAD rather than rebuilt, so every key neither this module
    nor its caller knows about survives the rewrite — the item-attributable
    repetition count among them, which the clause requires a recovery observation
    to leave exactly as it found it.
    """
    return {
        **dict(recorded.record),
        _ATTEMPT_FIELD: {
            **dict(recorded.attempt),
            _CLAIM_RECEIPT_FIELD: receipts.claim,
            _EXECUTION_RECEIPT_FIELD: receipts.execution,
            _OUTCOME_RECEIPT_FIELD: receipts.outcome,
        },
    }


def _outcome_receipt(*, records: ExecutionRecords) -> str | None:
    """The terminal outcome, with its pull request or its failure stage.

    The two trailers are not interchangeable and each is the only route to that
    terminal's evidence: a green run is reached through the pull request it
    produced and a failed one through the stage it died in. A terminal carrying
    NEITHER still yields the bare status rather than no receipt at all, because
    the run did reach a terminal and dropping the receipt there would report an
    executed attempt as one that never ran.
    """
    status = records.outcome_status
    if status is None:
        return None
    if records.pr_number is not None:
        return f"{status} pull request {records.pr_number}"
    if records.outcome_stage is not None:
        return f"{status} at failure stage {records.outcome_stage}"
    return status


def _outcome_object(
    *,
    record: Mapping[str, object],
    work_item_id: str,
) -> dict[str, Any] | None:
    """One terminal-outcome journal record's own payload, for this item only."""
    if record.get(_STAGE_FIELD) != _OUTCOME_STAGE:
        return None
    outcome = record.get(_OUTCOME_FIELD)
    if not isinstance(outcome, dict):
        return None
    fields = cast("dict[str, Any]", outcome)
    if fields.get(_WORK_ITEM_FIELD) != work_item_id:
        return None
    return fields


def _pr_number(*, value: object) -> int | None:
    """A plain pull-request number; `bool` is rejected because it subclasses `int`."""
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value


def _text(*, value: object) -> str | None:
    """A non-blank string, or `None` for anything else."""
    if not isinstance(value, str):
        return None
    return value.strip() or None

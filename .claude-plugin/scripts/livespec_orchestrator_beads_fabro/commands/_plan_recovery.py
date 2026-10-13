"""Typed causal recovery: the one way an expired plan obligation reopens.

PURE. `contracts.md` section "Required result, budget and progress epoch" fixes
what an attempt must carry: "A changed approach MUST be a typed causal recovery
event naming the unresolved obligation, previous epoch, measured failure
evidence, cause classification, executable authorized next operation, stable
unique attempt id and bounded attempt deadline. Its attempt budget MUST NOT
replace or postpone the original obligation deadline. A prose `approach:` line,
acknowledgment, repair-child milestone or cosmetic pointer rewrite MUST NOT
qualify."

TWO INDEPENDENT GATES DECIDE THE NEXT OPERATION, and both are required. The
operation must be in `EXECUTABLE_OPERATIONS` — a CLOSED grammar of operations
this fleet can actually run — AND it must equal the one
`authorized_recovery_operation` derives for the measured cause. Neither alone is
sufficient, and the reason is a measured defect rather than caution: the draft
validator this module replaces derived the authorized operation from the
pointer's own `ref` and then treated EQUALITY as authorization, so a caller that
authored the ref authorized itself. Measured on `bd-ib-zi5ygh`, it accepted
`next_operation="I will try a different approach."` with a host cause and
`"diagnose-this-is-not-a-supported-operation"` with an unknown cause. The
grammar refuses the first pair because prose names no operation; it refuses the
second because a `diagnose-` PREFIX is not a supported operation, only a shape
that resembles one.

THE GRAMMAR IS CLOSED FOR THE SAME REASON THE RESULT-REFERENCE KINDS ARE. An
open grammar would admit a typo and an invented token on identical evidence, and
an invented token is exactly what "merely hardcoding a previously invented token
does not make it executable" names. Every member below has a real executor:
`impl:<item>` and `diagnose-plan-progress:<epic>` run through this plugin's drive
surface, and the four spec operations run through the Livespec Driver — which is
why the absence of a drive handler for THOSE is not a defect.

THE CAUSE DECIDES WHICH OPERATION IS AUTHORIZED, not the caller. "Unknown causes
require diagnosis and known host causes require bounded host recovery" — so an
unknown cause authorizes ONLY the plan-progress diagnosis, and a host or
item-attributable cause authorizes only the POINTER'S OWN operation, re-run
under the attempt's bound. A caller cannot widen that by naming something else,
because the derived operation is then matched for equality.

THE DERIVED OPERATION IS ITSELF GRAMMAR-CHECKED, which is the half the draft
skipped. A pointer whose `ref` is prose derives a prose "operation", and an
equality test against it passes. Checking the derived value too means an
unusable pointer authorizes NOTHING rather than authorizing its own text.

WHY THE ITEM-ATTRIBUTABLE COUNT LIVES IN THE RECOVERY RECORD. "Unknown causes
require diagnosis and known host causes require bounded host recovery; neither
increments or resets the item-attributable repetition count." The count is
therefore a function of the CAUSE of each attempt, and keeping it beside the
attempt that caused it is what makes a host or unknown attempt structurally
unable to move it — as opposed to a separate counter each arm must remember not
to touch.

WHY A FRESH ATTEMPT MAY CARRY NO RECEIPTS. "A fresh event authorizes one
recovery attempt; recording it is not evidence that the command executed or that
the target was fulfilled. Claim, execution and outcome receipts MUST remain
distinct." An attempt arriving with an execution receipt already filled in is
asserting its own execution, so it is refused rather than recorded: the receipts
are written by whatever OBSERVES the claim, the run and the outcome, each
separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction

__all__: list[str] = [
    "CAUSES",
    "CAUSE_HOST",
    "CAUSE_ITEM",
    "CAUSE_UNKNOWN",
    "DIAGNOSIS_OPERATION_PREFIX",
    "CausalRecovery",
    "RecoveryRefusal",
    "authorized_recovery_operation",
    "is_executable_operation",
    "item_attributable_attempts",
    "recovery_record",
    "validate_causal_recovery",
]

CAUSE_HOST = "host"
CAUSE_ITEM = "item"
CAUSE_UNKNOWN = "unknown"

# CLOSED, in the order the clause discusses them. `item` is the only cause that
# attributes the failure to the work itself, and so the only one that moves the
# repetition count.
CAUSES: tuple[str, ...] = (CAUSE_HOST, CAUSE_ITEM, CAUSE_UNKNOWN)

DIAGNOSIS_OPERATION_PREFIX = "diagnose-plan-progress:"

_WORK_ITEM_ID = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?:\.\d+)?"
_SPEC_TOPIC = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_SPEC_OPERATIONS = "propose-change|revise|critique|prune-history"

# Every member has a real executor. `impl:` and the plan-progress diagnosis run
# through this plugin's own drive surface; the four spec operations run through
# the Livespec Driver.
EXECUTABLE_OPERATIONS: tuple[str, ...] = (
    rf"impl:{_WORK_ITEM_ID}",
    rf"{DIAGNOSIS_OPERATION_PREFIX}{_WORK_ITEM_ID}",
    rf"(?:{_SPEC_OPERATIONS}):{_SPEC_TOPIC}",
)
_EXECUTABLE_OPERATION = re.compile("|".join(EXECUTABLE_OPERATIONS))

_ATTEMPT_FIELD = "attempt"
_ITEM_ATTEMPTS_FIELD = "item_attributable_attempts"


@dataclass(frozen=True, kw_only=True)
class CausalRecovery:
    """Evidence and authority for exactly ONE bounded recovery attempt.

    The three receipts are present so a LATER observer can fill them in on the
    recorded attempt; a FRESH attempt supplying any of them is refused, because
    recording an attempt is not evidence that its command ran.
    """

    required_result: object
    previous_epoch: int
    failure_evidence: str
    cause: str
    next_operation: str
    attempt_id: str
    attempt_deadline: str
    claim_receipt: str | None = None
    execution_receipt: str | None = None
    outcome_receipt: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecoveryRefusal:
    """Why one recovery attempt is not a fresh, causal, executable attempt."""

    detail: str


def is_executable_operation(*, operation: str) -> bool:
    """Whether an operation is in the closed grammar this fleet can execute."""
    return _EXECUTABLE_OPERATION.fullmatch(operation) is not None


def authorized_recovery_operation(*, action: NextAction, epic_id: str, cause: str) -> str | None:
    """The ONE operation this cause authorizes, or `None` when none is.

    The returned value is itself grammar-checked, so a pointer whose `ref` is
    prose authorizes NOTHING rather than authorizing its own text.
    """
    if cause == CAUSE_UNKNOWN:
        candidate = f"{DIAGNOSIS_OPERATION_PREFIX}{epic_id}"
    elif cause in (CAUSE_HOST, CAUSE_ITEM):
        candidate = _pointer_operation(action=action)
    else:
        return None
    if candidate == "" or not is_executable_operation(operation=candidate):
        return None
    return candidate


def validate_causal_recovery(  # noqa: PLR0911 -- one refusal per requirement the clause names; merging them would misreport which is unmet.
    *,
    recovery: CausalRecovery,
    action: NextAction,
    epic_id: str,
    current_epoch: int,
    current_result_identity: str,
    now: str,
) -> RecoveryRefusal | None:
    """Admit only a fresh, causal, executable, authorized attempt.

    The checks run in the clause's own order, and the order matters for the
    REPORT rather than the verdict: a reader told "the attempt deadline has
    passed" about an attempt that also named the wrong obligation would fix the
    deadline and meet the same refusal again.
    """
    parsed = parse_result_reference(value=recovery.required_result)
    if not isinstance(parsed, ResultReference) or parsed.identity != current_result_identity:
        return RecoveryRefusal(
            detail=(
                "causal recovery must name the unresolved obligation" f" {current_result_identity}"
            )
        )
    if recovery.previous_epoch != current_epoch:
        return RecoveryRefusal(
            detail=(
                f"causal recovery names previous epoch {recovery.previous_epoch},"
                f" but the chain stands at epoch {current_epoch}"
            )
        )
    if recovery.failure_evidence.strip() == "":
        return RecoveryRefusal(detail="causal recovery requires measured failure evidence")
    if recovery.cause not in CAUSES:
        return RecoveryRefusal(
            detail=f"causal recovery cause {recovery.cause!r} is not one of {CAUSES}"
        )
    if recovery.attempt_id.strip() == "":
        return RecoveryRefusal(detail="causal recovery requires a stable unique attempt id")
    operation_refusal = _operation_refusal(recovery=recovery, action=action, epic_id=epic_id)
    if operation_refusal is not None:
        return operation_refusal
    if instant_expired(until=recovery.attempt_deadline, now=now):
        return RecoveryRefusal(
            detail=(
                f"causal recovery attempt deadline {recovery.attempt_deadline} has already"
                " passed, so it bounds nothing"
            )
        )
    if (recovery.claim_receipt, recovery.execution_receipt, recovery.outcome_receipt) != (
        None,
        None,
        None,
    ):
        return RecoveryRefusal(
            detail=(
                "a fresh causal recovery attempt cannot assert a claim, execution or outcome"
                " receipt; recording an attempt is not evidence that its command ran"
            )
        )
    return None


def recovery_record(*, recovery: CausalRecovery, prior: AuthorityState, now: str) -> dict[str, Any]:
    """Render an admitted attempt for the authority's `last_recovery_attempt`.

    The item-attributable count rides WITH the attempt, so a host or unknown
    cause is structurally unable to move it rather than relying on each arm
    remembering not to.
    """
    increment = 1 if recovery.cause == CAUSE_ITEM else 0
    return {
        _ATTEMPT_FIELD: {
            "attempt_id": recovery.attempt_id,
            "previous_epoch": recovery.previous_epoch,
            "cause": recovery.cause,
            "failure_evidence": recovery.failure_evidence,
            "next_operation": recovery.next_operation,
            "attempt_deadline": recovery.attempt_deadline,
            "recorded_at": now,
            "claim_receipt": recovery.claim_receipt,
            "execution_receipt": recovery.execution_receipt,
            "outcome_receipt": recovery.outcome_receipt,
        },
        _ITEM_ATTEMPTS_FIELD: item_attributable_attempts(authority=prior) + increment,
    }


def item_attributable_attempts(*, authority: AuthorityState) -> int:
    """How many attempts so far blamed the WORK rather than the host or the unknown.

    Reads as zero for an authority that has recorded none and for a record this
    reader cannot parse: the count exists to bound re-dispatch of a failing
    item, and inventing a nonzero one from an unreadable record would park work
    on evidence nobody could read.
    """
    record = authority.last_recovery_attempt
    if not isinstance(record, dict):
        return 0
    counted = cast("dict[str, Any]", record).get(_ITEM_ATTEMPTS_FIELD)
    if not isinstance(counted, int) or isinstance(counted, bool) or counted < 0:
        return 0
    return counted


def _operation_refusal(
    *,
    recovery: CausalRecovery,
    action: NextAction,
    epic_id: str,
) -> RecoveryRefusal | None:
    """Both gates, each reported as the distinct thing it measured."""
    if not is_executable_operation(operation=recovery.next_operation):
        return RecoveryRefusal(
            detail=(
                f"causal recovery next operation {recovery.next_operation!r} is not an"
                " executable operation; prose, an acknowledgment and an unsupported"
                " token never qualify"
            )
        )
    authorized = authorized_recovery_operation(action=action, epic_id=epic_id, cause=recovery.cause)
    if authorized is None:
        return RecoveryRefusal(
            detail=(
                f"no executable operation is authorized for cause {recovery.cause!r} on a"
                f" {action.kind} pointer"
            )
        )
    if recovery.next_operation != authorized:
        return RecoveryRefusal(
            detail=(
                f"cause {recovery.cause!r} authorizes only {authorized!r}, not"
                f" {recovery.next_operation!r}"
            )
        )
    return None


def _pointer_operation(*, action: NextAction) -> str:
    """The pointer's OWN executable operation, re-run under the attempt's bound."""
    ref = action.ref.strip()
    if ref == "":
        return ""
    if action.kind == "impl":
        return f"impl:{ref}"
    if action.kind == "spec-op":
        return ref
    return ""

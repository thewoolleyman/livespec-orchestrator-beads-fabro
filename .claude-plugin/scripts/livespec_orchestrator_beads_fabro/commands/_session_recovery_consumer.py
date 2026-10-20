"""The one consumer pass a daemon drives, and the result it can act on.

This is the orchestrator-side consumer API the "Launch obligations and consumed
recovery" clause assigns to this repository: "The overseer repository owns and
must ratify its consumer/service realization; this repository owns registration,
interoperable consumer execution receipts, action reconciliation and released
integration proof." No daemon lives here — the schedule, the service and the
takeover are the overseer's. What lives here is ONE pass over ONE attempt,
returning everything a scheduler needs to decide whether the 60-second bound was
met and what to wake for next.

THE ORDER OF THE PASS IS THE CONTRACT, and each step is where it is for a
measured reason.

RECEIPT FIRST, because "the existing ack command records receipt ONLY" and the
clause separates it from every later transition: a pass that claimed before
acknowledging would lose the evidence that a notification arrived at all when the
claim is refused to it.

CLAIM SECOND, before safety and before any reading, because the claim is what
makes this consumer's later observations ITS OWN. A pass that graded safety first
and then lost the claim would have spent its reading on an attempt it may not
touch — and, worse, a pass that executed before claiming is the duplicate the
whole fencing exists to prevent.

SAFETY THIRD, between the claim and the action, which is the position the clause
fixes: "The consumer MUST observe and queue recovery without interrupting or
abandoning protected work and record the specific barrier kind ... within 60
seconds of the failure/expiry trigger." So the deferral is recorded by a consumer
that HOLDS the attempt — a deferral written without a claim could be overwritten
by a competitor — and it is recorded BEFORE the action is selected, since
selecting one would spend readings on work that cannot proceed.

ACTION FOURTH, so no command is ever named before current ledger, forge and
recorded remote-factory evidence has been re-read. The selection is
`_session_recovery_action`'s, and this module adds nothing to it.

EXECUTION LAST, and the reconciled next action after it, because the next action
is the one the command that RAN left behind. A pass that recorded the next action
up front would be publishing a prediction under an execution receipt's authority.

WHY A DEFERRAL PRESERVES THE OBLIGATION STRUCTURALLY. The deferral writes exactly
one transition and returns. There is no branch here that can touch the original
deadline, the epoch or the required result — those are read back out of the
record and REPORTED, which is what makes "retaining the original
obligation/deadline history" checkable from the outcome alone rather than a
property of this module's care.

WHY THE OUTCOME REPORTS A LATENCY THAT MAY BE ABSENT. The scheduler's bound is on
actual execution, and `_session_recovery_consumption` measures it from the
notification; where either instant is unreadable the figure is omitted with its
diagnostic rather than reported as zero, because a fabricated zero is the most
convincing possible claim that a bound was met.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    AuthoritativeEvidence,
    SanctionedAction,
    select_sanctioned_action,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import (
    RecoveryEffectReader,
    SanctionedCommand,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_execution import (
    ExecutionRequest,
    execute_recovery,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import claim_recovery
from livespec_orchestrator_beads_fabro.commands._session_recovery_outcome import (
    CONSUMER_DEFERRED,
    CONSUMER_NOT_AUTHORIZED,
    CONSUMER_UNCLAIMED,
    ConsumerDecision,
    ConsumerOutcome,
    consumer_outcome,
    consumer_state,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_DEFERRED,
    TRANSITION_RECEIPT,
    TRANSITION_RECONCILED,
    append_recovery_transition,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import (
    SafetyState,
    SafetyVerdict,
    safety_verdict,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

__all__: list[str] = [
    "ConsumerRequest",
    "consume_recovery_obligation",
]


@dataclass(frozen=True, kw_only=True)
class ConsumerRequest:
    """One consumer's pass over one canonical attempt."""

    recovery_store_root: Path
    attempt_id: str
    consumer: str
    observed_at: float
    lease_seconds: float
    lock_budget: LockBudget | None = None


def consume_recovery_obligation(
    *,
    request: ConsumerRequest,
    evidence: AuthoritativeEvidence,
    safety: SafetyState,
    command: SanctionedCommand,
    reader: RecoveryEffectReader,
) -> ConsumerOutcome:
    """Acknowledge, claim, grade safety, reconcile the action, and execute once."""
    _ = append_recovery_transition(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        transition=TRANSITION_RECEIPT,
        observed_at=request.observed_at,
        detail={"consumer": request.consumer},
        lock_budget=request.lock_budget,
    )
    claim = claim_recovery(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        consumer=request.consumer,
        now=request.observed_at,
        lease_seconds=request.lease_seconds,
        lock_budget=request.lock_budget,
    )
    if not claim.granted:
        return _outcome(
            request=request,
            decision=ConsumerDecision(state=CONSUMER_UNCLAIMED, diagnostics=(claim.state,)),
            generation=claim.generation,
        )
    graded = safety_verdict(state=safety)
    if not graded.mutation_permitted:
        return _deferred(request=request, graded=graded, generation=claim.generation)
    return _authorized(
        request=request,
        action=select_sanctioned_action(evidence=evidence),
        generation=claim.generation,
        command=command,
        reader=reader,
    )


def _deferred(
    *, request: ConsumerRequest, graded: SafetyVerdict, generation: int
) -> ConsumerOutcome:
    """Record the specific barrier, and touch nothing else about the obligation."""
    _ = append_recovery_transition(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        transition=TRANSITION_DEFERRED,
        observed_at=request.observed_at,
        detail=_barrier_detail(graded=graded),
        lock_budget=request.lock_budget,
    )
    return _outcome(
        request=request,
        decision=ConsumerDecision(
            state=CONSUMER_DEFERRED, barrier=graded.barrier, diagnostics=graded.diagnostics
        ),
        generation=generation,
    )


def _barrier_detail(*, graded: SafetyVerdict) -> dict[str, object]:
    """The deferral's own record: which barrier, and how it is released.

    The release condition is carried only where a HOLD supplied one, because a
    commit hook and a Red-Green pair clear on their own and an invented release
    condition for them would tell an operator to wait for nothing.
    """
    hold = graded.hold
    detail: dict[str, object] = {"barrier": graded.barrier}
    if hold is not None:
        detail["authority"] = hold.authority
        detail["owner"] = hold.owner
        detail["reason"] = hold.reason
        detail["release_condition"] = hold.release_condition
    return detail


def _authorized(
    *,
    request: ConsumerRequest,
    action: SanctionedAction,
    generation: int,
    command: SanctionedCommand,
    reader: RecoveryEffectReader,
) -> ConsumerOutcome:
    """Execute the one action current evidence sanctioned, or report that none was."""
    if action.operation is None:
        return _outcome(
            request=request,
            decision=ConsumerDecision(
                state=CONSUMER_NOT_AUTHORIZED,
                diagnostics=(action.state, *action.diagnostics),
            ),
            generation=generation,
        )
    outcome = execute_recovery(
        request=ExecutionRequest(
            recovery_store_root=request.recovery_store_root,
            attempt_id=request.attempt_id,
            consumer=request.consumer,
            generation=generation,
            operation=action.operation,
            observed_at=request.observed_at,
            lock_budget=request.lock_budget,
        ),
        command=command,
        reader=reader,
    )
    if outcome.effect is not None:
        _ = append_recovery_transition(
            recovery_store_root=request.recovery_store_root,
            attempt_id=request.attempt_id,
            transition=TRANSITION_RECONCILED,
            observed_at=request.observed_at,
            detail={"next_action": outcome.effect.next_action},
            lock_budget=request.lock_budget,
        )
    return _outcome(
        request=request,
        decision=ConsumerDecision(
            state=consumer_state(execution_state=outcome.state),
            operation=action.operation,
            effect=outcome.effect,
            diagnostics=(outcome.state, *action.diagnostics),
        ),
        generation=generation,
    )


def _outcome(
    *, request: ConsumerRequest, decision: ConsumerDecision, generation: int
) -> ConsumerOutcome:
    """Report this pass through the one assembly that reads the record back."""
    return consumer_outcome(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        decision=decision,
        generation=generation,
    )

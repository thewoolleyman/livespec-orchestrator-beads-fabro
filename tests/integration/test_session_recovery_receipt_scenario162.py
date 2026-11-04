"""Scenario 162 — receipt is distinct from consumed recovery and fulfilled work.

`contracts.md` section "Launch obligations and consumed recovery": "Notification
production, receipt acknowledgement, consumer claim, execution start, execution
evidence, resulting next-action reconciliation and target-effect fulfillment MUST
be separate durable observations. Receipt or claim alone MUST NOT mark recovery
consumed. Successful recovery execution MUST NOT discharge the original result
unless the relay-owned authoritative reader establishes fulfillment."

Driven through the PUBLIC consumer surface — `consume_recovery_obligation` over a
real on-disk attempt store — rather than through the grade in isolation, because
the scenario's claim is about what a real pass leaves behind. A hand-built record
would satisfy every assertion here while saying nothing about the path a daemon
takes.

WHY THE UNCONSUMED LEG IS A REAL DEFERRED PASS AND NOT A SKIPPED ONE. The
scenario's first state is "a produced notification, receipt acknowledgement and
claimed recovery with no execution", and the only honest way to reach it is a
pass that acknowledged, claimed and then declined to mutate — which a valid HOLD
produces. Writing the three transitions by hand would reach the same record
without ever establishing that a consumer can arrive there.

WHY THE POSITIVE CONTROL IS THE SAME ATTEMPT CONTINUED. The second leg releases
the hold and lets the SAME attempt execute, so consumption becoming observable is
attributable to the execution rather than to a different fixture. A separate
attempt for the executed leg would agree with a build that marked every claimed
recovery consumed.

WHY FULFILLMENT IS ASSERTED AS AN ABSENCE OF VOCABULARY. There is no reader here
that could establish the relay-owned target effect, so the check is that the
consumption grade's own state set cannot express it and that the required-result
identity survives the pass untouched — which is what leaves the question with the
authority that owns it.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    AuthoritativeEvidence,
    Reading,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumer import (
    ConsumerRequest,
    consume_recovery_obligation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    CONSUMPTION_CONSUMED,
    CONSUMPTION_STATES,
    CONSUMPTION_UNCONSUMED,
    recovery_consumption,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect
from livespec_orchestrator_beads_fabro.commands._session_recovery_outcome import (
    CONSUMER_DEFERRED,
    CONSUMER_EXECUTED,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_CLAIMED,
    TRANSITION_DEFERRED,
    TRANSITION_EXECUTED,
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_RECONCILED,
    TRANSITION_STARTED,
    RecoveryAttempt,
    append_recovery_transition,
    observed_transitions,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import (
    HumanHold,
    SafetyState,
)

from tests.integration.session_recovery_doubles import RecordingCommand, RecordingLookup

_ATTEMPT_ID = "attempt-scenario162"
_ITEM = "bd-ib-dle6l3"
_EPIC = "bd-ib-jnpvh4"
_REQUIRED_RESULT = "pull_request_state #2700 state MERGED"
_DEADLINE = "2026-10-21T02:00:00Z"
_EPOCH = 14
_EFFECT = RecoveryEffect(
    operation=f"reconcile-merged:{_ITEM}",
    identity="gate:20261021T014500Z-7",
    next_action=f"impl:{_ITEM}",
)
_HOLD = HumanHold(
    authority="maintainer",
    reason="the fleet is frozen for the storage move",
    owner="thewoolleyman",
    release_condition="the storage move completes",
)


def _notified_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-scenario162",
            required_result_identity=_REQUIRED_RESULT,
            result_epoch=_EPOCH,
            original_deadline=_DEADLINE,
        ),
        opened_at=0.0,
    )
    _ = append_recovery_transition(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        transition=TRANSITION_NOTIFICATION,
        observed_at=200.0,
    )
    return store


def _payload(*, store: Path) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    )
    assert read.payload is not None
    return read.payload


def _request(*, store: Path, observed_at: float) -> ConsumerRequest:
    return ConsumerRequest(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        observed_at=observed_at,
        lease_seconds=30.0,
    )


def _evidence() -> AuthoritativeEvidence:
    return AuthoritativeEvidence(
        item_id=_ITEM,
        epic_id=_EPIC,
        recorded_next_operation=f"diagnose-plan-progress:{_EPIC}",
        recorded_operation_completed=True,
        ledger_status=Reading(value="active"),
        merged_pull_request=Reading(value="9117b1c8"),
        remote_run_outcome=Reading(value="succeeded"),
        local_gate_outcome="failed",
        recorded_epoch=_EPOCH,
        current_epoch=_EPOCH,
    )


def _safety(*, hold: HumanHold | None) -> SafetyState:
    return SafetyState(
        hold=hold,
        commit_hook_running=False,
        red_green_pair_open=False,
        session_idle=True,
        notification_unanswered=True,
        prose_deadline="we should be done by 14:25",
        stale_diagnostic=f"diagnose-plan-progress:{_EPIC}",
    )


def test_scenario_162_receipt_and_claim_leave_the_result_outstanding_until_execution(
    *, tmp_path: Path
) -> None:
    """Receipt and claim without execution, then execution, over ONE attempt."""
    store = _notified_store(tmp_path=tmp_path)
    command = RecordingCommand(effect=_EFFECT)
    lookup = RecordingLookup()

    acknowledged = consume_recovery_obligation(
        request=_request(store=store, observed_at=210.0),
        evidence=_evidence(),
        safety=_safety(hold=_HOLD),
        command=command,
        reader=lookup,
    )

    assert acknowledged.state == CONSUMER_DEFERRED
    assert acknowledged.generation == 1
    assert command.calls == []
    unconsumed = recovery_consumption(payload=_payload(store=store))
    assert unconsumed.state == CONSUMPTION_UNCONSUMED
    assert not unconsumed.consumed
    assert unconsumed.required_result_identity == _REQUIRED_RESULT
    assert unconsumed.original_deadline == _DEADLINE
    assert unconsumed.result_epoch == _EPOCH
    assert unconsumed.latency_seconds is None
    assert observed_transitions(payload=_payload(store=store)) == (
        TRANSITION_NOTIFICATION,
        TRANSITION_RECEIPT,
        TRANSITION_CLAIMED,
        TRANSITION_DEFERRED,
    )

    executed = consume_recovery_obligation(
        request=_request(store=store, observed_at=240.0),
        evidence=_evidence(),
        safety=_safety(hold=None),
        command=command,
        reader=lookup,
    )

    assert executed.state == CONSUMER_EXECUTED
    assert executed.effect == _EFFECT
    assert command.calls == [f"{_ATTEMPT_ID}:reconcile-merged:{_ITEM}"]
    consumed = recovery_consumption(payload=_payload(store=store))
    assert consumed.state == CONSUMPTION_CONSUMED
    assert consumed.consumed
    assert consumed.latency_seconds == 40.0
    assert observed_transitions(payload=_payload(store=store)) == (
        TRANSITION_NOTIFICATION,
        TRANSITION_RECEIPT,
        TRANSITION_CLAIMED,
        TRANSITION_DEFERRED,
        TRANSITION_STARTED,
        TRANSITION_EXECUTED,
        TRANSITION_RECONCILED,
    )

    assert CONSUMPTION_STATES == (CONSUMPTION_UNCONSUMED, CONSUMPTION_CONSUMED)
    assert consumed.required_result_identity == _REQUIRED_RESULT
    assert consumed.original_deadline == _DEADLINE
    assert consumed.result_epoch == _EPOCH
    # No pass here is ambiguous, so the durable-effect lookup is never needed:
    # both executions reported what they did.
    assert lookup.calls == []

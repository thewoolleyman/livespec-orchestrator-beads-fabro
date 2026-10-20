"""One consumer pass end to end: receipt, claim, safety, reconciliation, execution.

Scenario 164 of `SPECIFICATION/scenarios.md` asks a deferral to retain "the
original obligation and deadline" and to record "a specific safety-deferral
observation"; Scenario 162 asks every transition to stay separately observable.
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
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect
from livespec_orchestrator_beads_fabro.commands._session_recovery_execution import (
    EXECUTION_UNCERTAIN,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import claim_recovery
from livespec_orchestrator_beads_fabro.commands._session_recovery_outcome import (
    CONSUMER_CONVERGED,
    CONSUMER_DEFERRED,
    CONSUMER_EXECUTED,
    CONSUMER_NOT_AUTHORIZED,
    CONSUMER_UNCLAIMED,
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
    BARRIER_COMMIT_HOOK,
    BARRIER_HUMAN_HOLD,
    BARRIER_RED_GREEN_PAIR,
    HumanHold,
    SafetyState,
)

_ATTEMPT_ID = "attempt-dle6l3-consumer"
_ITEM = "bd-ib-dle6l3"
_EPIC = "bd-ib-jnpvh4"
_DEADLINE = "2026-10-20T23:45:00Z"
_EPOCH = 11
_EFFECT = RecoveryEffect(
    operation=f"reconcile-merged:{_ITEM}",
    identity="gate:20261020T234000Z-3",
    next_action=f"impl:{_ITEM}",
)
_HOLD = HumanHold(
    authority="maintainer",
    reason="the fleet is frozen for the storage move",
    owner="thewoolleyman",
    release_condition="the storage move completes",
)


class _Command:
    def __init__(self, *, effect: RecoveryEffect | None = _EFFECT) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def __call__(self, *, attempt_id: str, operation: str) -> RecoveryEffect | None:
        self.calls.append(f"{attempt_id}:{operation}")
        return self._effect


class _Reader:
    def __init__(self, *, effect: RecoveryEffect | None = None) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def observe(self, *, attempt_id: str) -> RecoveryEffect | None:
        self.calls.append(attempt_id)
        return self._effect


def _notified_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-consumer",
            required_result_identity="pull_request_state #2700 state MERGED",
            result_epoch=_EPOCH,
            original_deadline=_DEADLINE,
        ),
        opened_at=0.0,
    )
    _ = append_recovery_transition(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        transition=TRANSITION_NOTIFICATION,
        observed_at=100.0,
    )
    return store


def _payload(*, store: Path) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    )
    assert read.payload is not None
    return read.payload


def _request(*, store: Path, consumer: str = "overseerd@hp", observed_at: float) -> ConsumerRequest:
    return ConsumerRequest(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer=consumer,
        observed_at=observed_at,
        lease_seconds=30.0,
    )


def _evidence(
    *, merged: str = "9117b1c8", ledger: str = "active", item_id: str = _ITEM
) -> AuthoritativeEvidence:
    return AuthoritativeEvidence(
        item_id=item_id,
        epic_id=_EPIC,
        recorded_next_operation=f"diagnose-plan-progress:{_EPIC}",
        recorded_operation_completed=True,
        ledger_status=Reading(value=ledger),
        merged_pull_request=Reading(value=merged),
        remote_run_outcome=Reading(value="succeeded"),
        local_gate_outcome="failed",
        recorded_epoch=_EPOCH,
        current_epoch=_EPOCH,
    )


def _safety(
    *,
    hold: HumanHold | None = None,
    commit_hook_running: bool = False,
    red_green_pair_open: bool = False,
) -> SafetyState:
    return SafetyState(
        hold=hold,
        commit_hook_running=commit_hook_running,
        red_green_pair_open=red_green_pair_open,
        session_idle=True,
        notification_unanswered=True,
        prose_deadline="we should be done by 14:25",
        stale_diagnostic=f"diagnose-plan-progress:{_EPIC}",
    )


def test_one_pass_records_every_transition_and_executes_the_reconciled_action(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)
    command = _Command()

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert outcome.state == CONSUMER_EXECUTED
    assert outcome.executed
    assert outcome.operation == f"reconcile-merged:{_ITEM}"
    assert outcome.effect == _EFFECT
    assert outcome.generation == 1
    assert outcome.latency_seconds == 40.0
    assert outcome.original_deadline == _DEADLINE
    assert outcome.result_epoch == _EPOCH
    assert command.calls == [f"{_ATTEMPT_ID}:reconcile-merged:{_ITEM}"]

    assert observed_transitions(payload=_payload(store=store)) == (
        TRANSITION_NOTIFICATION,
        TRANSITION_RECEIPT,
        TRANSITION_STARTED,
        TRANSITION_EXECUTED,
        TRANSITION_RECONCILED,
    )


def test_a_valid_hold_defers_mutation_and_preserves_the_obligation_it_found(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)
    command = _Command()

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(hold=_HOLD),
        command=command,
        reader=_Reader(),
    )

    assert outcome.state == CONSUMER_DEFERRED
    assert outcome.deferred
    assert outcome.barrier == BARRIER_HUMAN_HOLD
    assert outcome.operation is None
    assert outcome.effect is None
    assert command.calls == []

    payload = _payload(store=store)
    assert observed_transitions(payload=payload) == (
        TRANSITION_NOTIFICATION,
        TRANSITION_RECEIPT,
        TRANSITION_DEFERRED,
    )
    assert outcome.original_deadline == _DEADLINE
    assert outcome.result_epoch == _EPOCH
    assert payload["original_deadline"] == _DEADLINE
    assert payload["required_result_identity"] == "pull_request_state #2700 state MERGED"
    assert _deferral_detail(payload=payload)["release_condition"] == "the storage move completes"


def _deferral_detail(*, payload: dict[str, object]) -> dict[str, object]:
    """The detail of the ONE deferral observation this record carries."""
    entries = payload["transitions"]
    assert isinstance(entries, list)
    details = [_detail(entry=one) for one in entries if _kind(entry=one) == TRANSITION_DEFERRED]
    assert len(details) == 1
    return details[0]


def _kind(*, entry: object) -> object:
    assert isinstance(entry, dict)
    return entry.get("transition")


def _detail(*, entry: object) -> dict[str, object]:
    assert isinstance(entry, dict)
    detail = entry.get("detail")
    assert isinstance(detail, dict)
    return detail


def test_an_active_commit_hook_defers_without_inventing_a_release_condition(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(commit_hook_running=True),
        command=_Command(),
        reader=_Reader(),
    )

    assert outcome.barrier == BARRIER_COMMIT_HOOK
    detail = _deferral_detail(payload=_payload(store=store))
    assert detail == {"barrier": BARRIER_COMMIT_HOOK}


def test_an_open_red_green_pair_defers_and_the_cleared_barrier_then_executes(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)
    command = _Command()

    deferred = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(red_green_pair_open=True),
        command=command,
        reader=_Reader(),
    )
    assert deferred.barrier == BARRIER_RED_GREEN_PAIR
    assert command.calls == []

    cleared = consume_recovery_obligation(
        request=_request(store=store, observed_at=150.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert cleared.state == CONSUMER_EXECUTED
    assert cleared.effect == _EFFECT
    assert command.calls == [f"{_ATTEMPT_ID}:reconcile-merged:{_ITEM}"]
    assert cleared.original_deadline == _DEADLINE
    assert cleared.latency_seconds == 50.0


def test_a_consumer_another_holds_the_lease_against_never_reaches_the_command(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)
    held = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer="overseerd@hp",
        now=140.0,
        lease_seconds=30.0,
    )
    assert held.granted
    command = _Command()

    outcome = consume_recovery_obligation(
        request=_request(store=store, consumer="overseerd@vps", observed_at=141.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert outcome.state == CONSUMER_UNCLAIMED
    assert outcome.operation is None
    assert command.calls == []
    assert outcome.original_deadline == _DEADLINE
    assert TRANSITION_CLAIMED not in observed_transitions(payload=_payload(store=store))


def test_evidence_that_authorizes_nothing_executes_nothing_and_says_so(*, tmp_path: Path) -> None:
    store = _notified_store(tmp_path=tmp_path)
    command = _Command()

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(merged=""),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert outcome.state == CONSUMER_NOT_AUTHORIZED
    assert outcome.operation is None
    assert command.calls == []


def test_an_ambiguous_execution_is_reported_verbatim_rather_than_as_one_failure(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(),
        command=_Command(effect=None),
        reader=_Reader(),
    )

    assert outcome.state == EXECUTION_UNCERTAIN
    assert not outcome.executed
    assert outcome.effect is None
    assert TRANSITION_RECONCILED not in observed_transitions(payload=_payload(store=store))


def test_a_pass_after_an_ambiguous_one_looks_the_effect_up_before_retrying(
    *, tmp_path: Path
) -> None:
    store = _notified_store(tmp_path=tmp_path)
    _ = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(),
        command=_Command(effect=None),
        reader=_Reader(),
    )

    retry_command = _Command()
    lookup = _Reader(effect=_EFFECT)
    recovered = consume_recovery_obligation(
        request=_request(store=store, observed_at=141.0),
        evidence=_evidence(),
        safety=_safety(),
        command=retry_command,
        reader=lookup,
    )

    assert recovered.state == CONSUMER_CONVERGED
    assert recovered.effect == _EFFECT
    assert lookup.calls == [_ATTEMPT_ID]
    assert retry_command.calls == []
    assert TRANSITION_RECONCILED in observed_transitions(payload=_payload(store=store))


def test_a_second_pass_converges_on_the_effect_the_first_one_produced(*, tmp_path: Path) -> None:
    store = _notified_store(tmp_path=tmp_path)
    command = _Command()
    _ = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    again = consume_recovery_obligation(
        request=_request(store=store, observed_at=141.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert again.state == CONSUMER_CONVERGED
    assert again.effect == _EFFECT
    assert command.calls == [f"{_ATTEMPT_ID}:reconcile-merged:{_ITEM}"]


def test_an_attempt_that_was_never_opened_reports_no_obligation_fields(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"
    command = _Command()

    outcome = consume_recovery_obligation(
        request=_request(store=store, observed_at=140.0),
        evidence=_evidence(),
        safety=_safety(),
        command=command,
        reader=_Reader(),
    )

    assert outcome.state == CONSUMER_UNCLAIMED
    assert outcome.original_deadline is None
    assert outcome.result_epoch is None
    assert outcome.latency_seconds is None
    assert command.calls == []

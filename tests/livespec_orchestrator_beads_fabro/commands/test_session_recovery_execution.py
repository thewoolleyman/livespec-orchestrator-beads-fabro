"""One supported command effect, however many triggers and consumers arrive.

Scenario 163 of `SPECIFICATION/scenarios.md`: "serialized generation-fenced
ownership yields one supported command effect", and after an ambiguous receipt a
replacement consumer "queries the durable command effect before retrying" while
"an unobservable lookup preserves uncertainty rather than executing twice".
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    recovery_consumption,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import (
    RecoveryEffect,
    recorded_effect,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_execution import (
    EXECUTION_ABSENT,
    EXECUTION_ALREADY_EXECUTED,
    EXECUTION_EFFECT_RECOVERED,
    EXECUTION_EXECUTED,
    EXECUTION_FENCED,
    EXECUTION_UNAVAILABLE,
    EXECUTION_UNCERTAIN,
    EXECUTION_UNCLAIMED,
    EXECUTION_UNOBSERVABLE,
    ExecutionRequest,
    execute_recovery,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import claim_recovery
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_EXECUTED,
    TRANSITION_STARTED,
    RecoveryAttempt,
    observed_transitions,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    wait_store_lock,
)

_ATTEMPT_ID = "attempt-dle6l3-execution"
_OPERATION = "reconcile-merged:bd-ib-dle6l3"
_EFFECT = RecoveryEffect(
    operation=_OPERATION,
    identity="gate:20261020T210000Z-1",
    next_action="impl:bd-ib-dle6l3",
)


class _Command:
    """A sanctioned command that records every invocation it was asked to make."""

    def __init__(self, *, effect: RecoveryEffect | None = _EFFECT) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def __call__(self, *, attempt_id: str, operation: str) -> RecoveryEffect | None:
        self.calls.append(f"{attempt_id}:{operation}")
        return self._effect


class _Reader:
    """A durable effect lookup, and a count of how often it was consulted."""

    def __init__(self, *, effect: RecoveryEffect | None) -> None:
        self.calls: list[str] = []
        self._effect = effect

    def observe(self, *, attempt_id: str) -> RecoveryEffect | None:
        self.calls.append(attempt_id)
        return self._effect


def _opened_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-execution",
            required_result_identity="pull_request_state #2700 state MERGED",
            result_epoch=6,
            original_deadline="2026-10-20T22:00:00Z",
        ),
        opened_at=0.0,
    )
    return store


def _payload(*, store: Path, attempt_id: str = _ATTEMPT_ID) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=attempt_id)
    )
    assert read.payload is not None
    return read.payload


def _granted(*, store: Path, consumer: str, now: float) -> int:
    claim = claim_recovery(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        consumer=consumer,
        now=now,
        lease_seconds=30.0,
    )
    assert claim.granted
    return claim.generation


def _request(
    *,
    store: Path,
    consumer: str,
    generation: int,
    observed_at: float,
    attempt_id: str = _ATTEMPT_ID,
    lock_budget: LockBudget | None = None,
) -> ExecutionRequest:
    return ExecutionRequest(
        recovery_store_root=store,
        attempt_id=attempt_id,
        consumer=consumer,
        generation=generation,
        operation=_OPERATION,
        observed_at=observed_at,
        lock_budget=lock_budget,
    )


def test_a_duplicate_trigger_converges_on_the_one_effect_already_recorded(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    generation = _granted(store=store, consumer="overseerd@hp", now=10.0)
    command = _Command()
    reader = _Reader(effect=None)

    first = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=generation, observed_at=11.0
        ),
        command=command,
        reader=reader,
    )
    second = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=generation, observed_at=12.0
        ),
        command=command,
        reader=reader,
    )

    assert first.state == EXECUTION_EXECUTED
    assert first.converged
    assert first.effect == _EFFECT
    assert second.state == EXECUTION_ALREADY_EXECUTED
    assert second.effect == _EFFECT
    assert command.calls == [f"{_ATTEMPT_ID}:{_OPERATION}"]
    assert reader.calls == []

    payload = _payload(store=store)
    assert observed_transitions(payload=payload) == (TRANSITION_STARTED, TRANSITION_EXECUTED)
    assert recorded_effect(payload=payload) == _EFFECT
    assert recovery_consumption(payload=payload).consumed


def test_a_replacement_consumer_recovers_an_ambiguous_effect_rather_than_retrying(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    first_generation = _granted(store=store, consumer="overseerd@hp", now=10.0)
    ambiguous = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=first_generation, observed_at=11.0
        ),
        command=_Command(effect=None),
        reader=_Reader(effect=None),
    )
    assert ambiguous.state == EXECUTION_UNCERTAIN
    assert not ambiguous.converged

    replacement_generation = _granted(store=store, consumer="overseerd@vps", now=500.0)
    replacement_command = _Command()
    reader = _Reader(effect=_EFFECT)

    recovered = execute_recovery(
        request=_request(
            store=store,
            consumer="overseerd@vps",
            generation=replacement_generation,
            observed_at=501.0,
        ),
        command=replacement_command,
        reader=reader,
    )

    assert recovered.state == EXECUTION_EFFECT_RECOVERED
    assert recovered.effect == _EFFECT
    assert replacement_command.calls == []
    assert reader.calls == [_ATTEMPT_ID]
    assert recorded_effect(payload=_payload(store=store)) == _EFFECT


def test_an_unobservable_lookup_preserves_uncertainty_instead_of_executing_twice(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    generation = _granted(store=store, consumer="overseerd@hp", now=10.0)
    _ = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=generation, observed_at=11.0
        ),
        command=_Command(effect=None),
        reader=_Reader(effect=None),
    )

    retry_command = _Command()
    blind_reader = _Reader(effect=None)
    uncertain = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=generation, observed_at=12.0
        ),
        command=retry_command,
        reader=blind_reader,
    )

    assert uncertain.state == EXECUTION_UNCERTAIN
    assert uncertain.effect is None
    assert retry_command.calls == []
    assert blind_reader.calls == [_ATTEMPT_ID]
    assert recorded_effect(payload=_payload(store=store)) is None
    assert not recovery_consumption(payload=_payload(store=store)).consumed


def test_a_superseded_consumer_cannot_execute_and_its_refusal_is_counted(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    displaced = _granted(store=store, consumer="overseerd@hp", now=10.0)
    _ = _granted(store=store, consumer="overseerd@vps", now=500.0)
    command = _Command()

    fenced = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=displaced, observed_at=501.0
        ),
        command=command,
        reader=_Reader(effect=_EFFECT),
    )

    assert fenced.state == EXECUTION_FENCED
    assert fenced.effect is None
    assert command.calls == []
    assert _payload(store=store)["fenced_count"] == 1
    assert observed_transitions(payload=_payload(store=store)) == ()


def test_an_unclaimed_attempt_refuses_execution_without_claiming_itself(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    command = _Command()

    unclaimed = execute_recovery(
        request=_request(store=store, consumer="overseerd@hp", generation=1, observed_at=11.0),
        command=command,
        reader=_Reader(effect=None),
    )

    assert unclaimed.state == EXECUTION_UNCLAIMED
    assert command.calls == []
    assert _payload(store=store)["holder"] is None


def test_an_absent_attempt_and_an_unreadable_one_never_run_the_command(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    command = _Command()

    absent = execute_recovery(
        request=_request(
            store=store,
            consumer="overseerd@hp",
            generation=1,
            observed_at=11.0,
            attempt_id="attempt-never-opened",
        ),
        command=command,
        reader=_Reader(effect=None),
    )

    unreadable_path = recovery_record_path(
        recovery_store_root=store, attempt_id="attempt-unreadable"
    )
    unreadable_path.mkdir(parents=True)
    unreadable = execute_recovery(
        request=_request(
            store=store,
            consumer="overseerd@hp",
            generation=1,
            observed_at=12.0,
            attempt_id="attempt-unreadable",
        ),
        command=command,
        reader=_Reader(effect=None),
    )

    assert absent.state == EXECUTION_ABSENT
    assert unreadable.state == EXECUTION_UNOBSERVABLE
    assert command.calls == []


def test_a_contended_store_reports_unavailability_without_running_the_command(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    generation = _granted(store=store, consumer="overseerd@hp", now=10.0)
    command = _Command()

    with wait_store_lock(wait_store_root=store) as acquired:
        assert acquired
        unavailable = execute_recovery(
            request=_request(
                store=store,
                consumer="overseerd@hp",
                generation=generation,
                observed_at=12.0,
                lock_budget=LockBudget(
                    deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None
                ),
            ),
            command=command,
            reader=_Reader(effect=None),
        )

    assert unavailable.state == EXECUTION_UNAVAILABLE
    assert command.calls == []
    assert recorded_effect(payload=_payload(store=store)) is None


def test_an_effect_that_cannot_be_recorded_is_not_reported_as_an_execution(
    *, tmp_path: Path
) -> None:
    """The record can vanish between the fence check and the receipt's own write."""
    store = _opened_store(tmp_path=tmp_path)
    generation = _granted(store=store, consumer="overseerd@hp", now=10.0)
    command = _Command()

    class _Vanishing:
        """A command whose own run removes the attempt it was executing for."""

        def __init__(self) -> None:
            self.calls: list[str] = []

        def __call__(self, *, attempt_id: str, operation: str) -> RecoveryEffect | None:
            self.calls.append(f"{attempt_id}:{operation}")
            recovery_record_path(recovery_store_root=store, attempt_id=attempt_id).unlink()
            return _EFFECT

    vanishing = _Vanishing()
    outcome = execute_recovery(
        request=_request(
            store=store, consumer="overseerd@hp", generation=generation, observed_at=11.0
        ),
        command=vanishing,
        reader=_Reader(effect=None),
    )

    assert outcome.state == EXECUTION_UNAVAILABLE
    assert outcome.effect is None
    assert vanishing.calls == [f"{_ATTEMPT_ID}:{_OPERATION}"]
    assert command.calls == []

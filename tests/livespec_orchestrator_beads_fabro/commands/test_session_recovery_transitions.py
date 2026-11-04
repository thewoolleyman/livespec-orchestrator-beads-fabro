"""Receipt, claim, execution start, execution evidence and the reconciled next action.

Scenario 162 of `SPECIFICATION/scenarios.md` keeps those observations apart, and
`contracts.md` section "Launch obligations and consumed recovery" says why:
"Receipt or claim alone MUST NOT mark recovery consumed."
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    APPEND_ABSENT,
    APPEND_DUPLICATE,
    APPEND_RECORDED,
    APPEND_UNAVAILABLE,
    APPEND_UNKNOWN_TRANSITION,
    APPEND_UNOBSERVABLE,
    OPEN_ALREADY_OPEN,
    OPEN_OPENED,
    OPEN_UNAVAILABLE,
    RECOVERY_TRANSITIONS,
    TRANSITION_CLAIMED,
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
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    wait_store_lock,
)

_ATTEMPT_ID = "attempt-dle6l3-1"

_CONSUMER_TRANSITIONS = (
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_CLAIMED,
    TRANSITION_STARTED,
    TRANSITION_EXECUTED,
    TRANSITION_RECONCILED,
)


def _attempt(*, attempt_id: str = _ATTEMPT_ID) -> RecoveryAttempt:
    return RecoveryAttempt(
        attempt_id=attempt_id,
        operation_id="op-dle6l3-1",
        required_result_identity="pull_request_state #2700 state MERGED",
        result_epoch=4,
        original_deadline="2026-10-20T18:00:00Z",
    )


def _expired_budget() -> LockBudget:
    """A budget already spent, so a contended lock is refused without sleeping."""
    return LockBudget(deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None)


def _payload(*, store: Path, attempt_id: str = _ATTEMPT_ID) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=attempt_id)
    )
    assert read.payload is not None
    return read.payload


def _first_entry(*, payload: dict[str, object]) -> dict[str, object]:
    entries = payload["transitions"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    return first


def test_every_consumer_transition_is_its_own_durable_observation(*, tmp_path: Path) -> None:
    """The transitions the assertion names are written, and read back, apart."""
    store = tmp_path / "recovery"
    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=100.0)
        == OPEN_OPENED
    )

    for offset, transition in enumerate(_CONSUMER_TRANSITIONS):
        assert (
            append_recovery_transition(
                recovery_store_root=store,
                attempt_id=_ATTEMPT_ID,
                transition=transition,
                observed_at=110.0 + offset,
                detail={"source": transition},
            )
            == APPEND_RECORDED
        )

    payload = _payload(store=store)
    assert observed_transitions(payload=payload) == _CONSUMER_TRANSITIONS
    assert payload["duplicate_count"] == 0
    assert payload["required_result_identity"] == "pull_request_state #2700 state MERGED"
    assert payload["original_deadline"] == "2026-10-20T18:00:00Z"
    assert payload["result_epoch"] == 4


def test_a_duplicate_event_converges_on_the_first_observation(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"
    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=1.0)
        == OPEN_OPENED
    )
    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            transition=TRANSITION_RECEIPT,
            observed_at=2.0,
        )
        == APPEND_RECORDED
    )

    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            transition=TRANSITION_RECEIPT,
            observed_at=99.0,
        )
        == APPEND_DUPLICATE
    )

    payload = _payload(store=store)
    assert observed_transitions(payload=payload) == (TRANSITION_RECEIPT,)
    assert payload["duplicate_count"] == 1
    assert _first_entry(payload=payload)["observed_at"] == 2.0


def test_a_second_open_under_one_attempt_id_leaves_the_first_record_alone(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "recovery"
    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=5.0)
        == OPEN_OPENED
    )
    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            transition=TRANSITION_CLAIMED,
            observed_at=6.0,
        )
        == APPEND_RECORDED
    )

    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=500.0)
        == OPEN_ALREADY_OPEN
    )

    payload = _payload(store=store)
    assert payload["opened_at"] == 5.0
    assert observed_transitions(payload=payload) == (TRANSITION_CLAIMED,)


def test_a_transition_outside_the_closed_set_never_reaches_the_store(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"
    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=1.0)
        == OPEN_OPENED
    )

    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            transition="fulfilled",
            observed_at=2.0,
        )
        == APPEND_UNKNOWN_TRANSITION
    )

    assert "fulfilled" not in RECOVERY_TRANSITIONS
    assert observed_transitions(payload=_payload(store=store)) == ()


def test_an_absent_attempt_and_an_unreadable_one_answer_differently(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"

    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id="attempt-never-opened",
            transition=TRANSITION_RECEIPT,
            observed_at=1.0,
        )
        == APPEND_ABSENT
    )

    unreadable = recovery_record_path(recovery_store_root=store, attempt_id="attempt-unreadable")
    unreadable.mkdir(parents=True)
    assert (
        append_recovery_transition(
            recovery_store_root=store,
            attempt_id="attempt-unreadable",
            transition=TRANSITION_RECEIPT,
            observed_at=2.0,
        )
        == APPEND_UNOBSERVABLE
    )


def test_a_contended_store_reports_unavailability_rather_than_a_lost_observation(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "recovery"
    assert (
        open_recovery_attempt(recovery_store_root=store, attempt=_attempt(), opened_at=1.0)
        == OPEN_OPENED
    )

    with wait_store_lock(wait_store_root=store) as acquired:
        assert acquired
        assert (
            open_recovery_attempt(
                recovery_store_root=store,
                attempt=_attempt(attempt_id="attempt-contended"),
                opened_at=2.0,
                lock_budget=_expired_budget(),
            )
            == OPEN_UNAVAILABLE
        )
        assert (
            append_recovery_transition(
                recovery_store_root=store,
                attempt_id=_ATTEMPT_ID,
                transition=TRANSITION_RECEIPT,
                observed_at=3.0,
                lock_budget=_expired_budget(),
            )
            == APPEND_UNAVAILABLE
        )

    assert observed_transitions(payload=_payload(store=store)) == ()

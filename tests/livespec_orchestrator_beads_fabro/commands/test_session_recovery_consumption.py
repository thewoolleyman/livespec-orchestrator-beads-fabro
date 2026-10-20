"""A receipt and a claim leave recovery unconsumed; only execution evidence consumes it."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    CONSUMPTION_CONSUMED,
    CONSUMPTION_STATES,
    CONSUMPTION_UNCONSUMED,
    DIAGNOSTIC_LATENCY_UNOBSERVABLE,
    recovery_consumption,
    transition_instant,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_CLAIMED,
    TRANSITION_EXECUTED,
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_RECONCILED,
    RecoveryAttempt,
    append_recovery_transition,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
)

_ATTEMPT_ID = "attempt-dle6l3-consumption"


def _opened_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-consumption",
            required_result_identity="item_status bd-ib-dle6l3 status closed",
            result_epoch=7,
            original_deadline="2026-10-20T19:30:00Z",
        ),
        opened_at=10.0,
    )
    return store


def _observe(*, store: Path, transition: str, observed_at: float) -> None:
    _ = append_recovery_transition(
        recovery_store_root=store,
        attempt_id=_ATTEMPT_ID,
        transition=transition,
        observed_at=observed_at,
    )


def _payload(*, store: Path) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    )
    assert read.payload is not None
    return read.payload


def test_notification_receipt_and_claim_alone_leave_recovery_unconsumed(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    _observe(store=store, transition=TRANSITION_NOTIFICATION, observed_at=20.0)
    _observe(store=store, transition=TRANSITION_RECEIPT, observed_at=21.0)
    _observe(store=store, transition=TRANSITION_CLAIMED, observed_at=22.0)

    graded = recovery_consumption(payload=_payload(store=store))

    assert graded.state == CONSUMPTION_UNCONSUMED
    assert not graded.consumed
    assert graded.observed == (TRANSITION_NOTIFICATION, TRANSITION_RECEIPT, TRANSITION_CLAIMED)
    assert graded.latency_seconds is None
    assert graded.diagnostics == (DIAGNOSTIC_LATENCY_UNOBSERVABLE,)
    assert graded.required_result_identity == "item_status bd-ib-dle6l3 status closed"
    assert graded.original_deadline == "2026-10-20T19:30:00Z"
    assert graded.result_epoch == 7


def test_execution_evidence_is_what_makes_consumption_separately_observable(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)
    _observe(store=store, transition=TRANSITION_NOTIFICATION, observed_at=30.0)
    _observe(store=store, transition=TRANSITION_RECEIPT, observed_at=31.0)
    _observe(store=store, transition=TRANSITION_CLAIMED, observed_at=32.0)
    _observe(store=store, transition=TRANSITION_EXECUTED, observed_at=47.5)
    _observe(store=store, transition=TRANSITION_RECONCILED, observed_at=48.0)

    graded = recovery_consumption(payload=_payload(store=store))

    assert graded.state == CONSUMPTION_CONSUMED
    assert graded.consumed
    assert graded.latency_seconds == 17.5
    assert graded.diagnostics == ()
    assert graded.original_deadline == "2026-10-20T19:30:00Z"


def test_no_consumption_state_claims_the_relay_owned_target_fulfillment() -> None:
    """The grade cannot report fulfillment, because its vocabulary has no such word."""
    assert CONSUMPTION_STATES == (CONSUMPTION_UNCONSUMED, CONSUMPTION_CONSUMED)
    assert "fulfilled" not in CONSUMPTION_STATES


def test_an_unreadable_instant_is_omitted_rather_than_reported_as_zero(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    _observe(store=store, transition=TRANSITION_EXECUTED, observed_at=60.0)
    payload = _payload(store=store)
    entries = payload["transitions"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["observed_at"] = "not a number"

    graded = recovery_consumption(payload=payload)

    assert graded.state == CONSUMPTION_CONSUMED
    assert graded.latency_seconds is None
    assert graded.diagnostics == (DIAGNOSTIC_LATENCY_UNOBSERVABLE,)
    assert transition_instant(payload=payload, transition=TRANSITION_EXECUTED) is None


def test_an_instant_is_read_from_the_first_observation_of_its_transition(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)
    _observe(store=store, transition=TRANSITION_NOTIFICATION, observed_at=70.0)
    _observe(store=store, transition=TRANSITION_NOTIFICATION, observed_at=900.0)
    payload = _payload(store=store)

    assert transition_instant(payload=payload, transition=TRANSITION_NOTIFICATION) == 70.0
    assert transition_instant(payload=payload, transition=TRANSITION_RECEIPT) is None
    assert recovery_consumption(payload=payload).duplicate_count == 1
    assert recovery_consumption(payload=payload).fenced_count == 0

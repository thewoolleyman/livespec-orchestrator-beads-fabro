"""The execution receipt: a complete triple, or no effect at all."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import (
    RecoveryEffect,
    record_recovery_effect,
    recorded_effect,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_EXECUTED,
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

_ATTEMPT_ID = "attempt-dle6l3-effect"
_EFFECT = RecoveryEffect(
    operation="reconcile-merged:bd-ib-dle6l3",
    identity="gate:20261020T220000Z-9",
    next_action="impl:bd-ib-dle6l3",
)


def _opened_store(*, tmp_path: Path) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-effect",
            required_result_identity="pull_request_state #2700 state MERGED",
            result_epoch=3,
            original_deadline="2026-10-20T23:00:00Z",
        ),
        opened_at=0.0,
    )
    return store


def _payload(*, store: Path) -> dict[str, object]:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    )
    assert read.payload is not None
    return read.payload


def test_the_effect_and_its_evidence_transition_land_in_one_write(*, tmp_path: Path) -> None:
    store = _opened_store(tmp_path=tmp_path)

    assert (
        record_recovery_effect(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            effect=_EFFECT,
            observed_at=40.0,
        )
        is True
    )

    payload = _payload(store=store)
    assert recorded_effect(payload=payload) == _EFFECT
    assert observed_transitions(payload=payload) == (TRANSITION_EXECUTED,)


def test_a_vanished_attempt_is_not_recreated_from_the_payload_being_written(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "recovery"

    assert (
        record_recovery_effect(
            recovery_store_root=store,
            attempt_id="attempt-never-opened",
            effect=_EFFECT,
            observed_at=40.0,
        )
        is False
    )
    assert not recovery_record_path(
        recovery_store_root=store, attempt_id="attempt-never-opened"
    ).exists()


def test_a_contended_store_reports_an_unwritten_receipt_rather_than_a_lost_one(
    *, tmp_path: Path
) -> None:
    store = _opened_store(tmp_path=tmp_path)

    with wait_store_lock(wait_store_root=store) as acquired:
        assert acquired
        written = record_recovery_effect(
            recovery_store_root=store,
            attempt_id=_ATTEMPT_ID,
            effect=_EFFECT,
            observed_at=40.0,
            lock_budget=LockBudget(deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None),
        )

    assert written is None
    assert recorded_effect(payload=_payload(store=store)) is None


@pytest.mark.parametrize(
    "recorded",
    [
        None,
        "reconcile-merged:bd-ib-dle6l3",
        {"operation": "reconcile-merged:bd-ib-dle6l3"},
        {"operation": "reconcile-merged:bd-ib-dle6l3", "identity": "gate:1"},
        {"operation": 7, "identity": "gate:1", "next_action": "impl:bd-ib-dle6l3"},
        {
            "operation": "reconcile-merged:bd-ib-dle6l3",
            "identity": "gate:1",
            "next_action": 7,
        },
    ],
)
def test_a_partial_or_mistyped_receipt_reads_as_no_effect(*, recorded: object) -> None:
    assert recorded_effect(payload={"effect": recorded}) is None


def test_the_record_payload_carries_every_field_of_the_receipt() -> None:
    assert _EFFECT.record_payload() == {
        "identity": "gate:20261020T220000Z-9",
        "next_action": "impl:bd-ib-dle6l3",
        "operation": "reconcile-merged:bd-ib-dle6l3",
    }

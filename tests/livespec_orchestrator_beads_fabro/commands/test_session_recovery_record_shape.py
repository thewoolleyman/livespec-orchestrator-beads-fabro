"""Bytes that are not a version-1 recovery record are unobservable, never half-read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    transition_instant,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_RECEIPT,
    RecoveryAttempt,
    observed_transitions,
    open_recovery_attempt,
    read_recovery_record,
    recovery_record_path,
    write_recovery_record,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_shape import (
    DIAGNOSTIC_INVALID_RECORD,
    DIAGNOSTIC_UNSUPPORTED_SCHEMA,
    RECOVERY_SCHEMA_VERSION,
    graded_recovery_payload,
)

_ATTEMPT_ID = "attempt-dle6l3-shape"


def _well_formed_payload() -> dict[str, object]:
    return {
        "attempt_id": _ATTEMPT_ID,
        "duplicate_count": 0,
        "effect": None,
        "fenced_count": 0,
        "generation": 0,
        "holder": None,
        "lease_expires_at": None,
        "opened_at": 1.0,
        "operation_id": "op-dle6l3-shape",
        "original_deadline": "2026-10-20T20:00:00Z",
        "required_result_identity": "item_status bd-ib-dle6l3 status closed",
        "result_epoch": 2,
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "transitions": [],
    }


def test_a_well_formed_payload_is_graded_as_a_record() -> None:
    """The positive control: without it, a grade refusing everything would pass below."""
    graded = graded_recovery_payload(loaded=_well_formed_payload())

    assert graded.diagnostic is None
    assert graded.payload is not None


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ({"schema_version": 2}, DIAGNOSTIC_UNSUPPORTED_SCHEMA),
        ({"generation": True}, DIAGNOSTIC_INVALID_RECORD),
        ({"result_epoch": -1}, DIAGNOSTIC_INVALID_RECORD),
        ({"original_deadline": 1761000000}, DIAGNOSTIC_INVALID_RECORD),
        ({"transitions": {}}, DIAGNOSTIC_INVALID_RECORD),
    ],
)
def test_each_unusable_record_shape_names_the_thing_it_failed(
    *, mutation: dict[str, object], diagnostic: str
) -> None:
    payload = _well_formed_payload()
    payload.update(mutation)

    graded = graded_recovery_payload(loaded=payload)

    assert graded.payload is None
    assert graded.diagnostic == diagnostic


def test_a_missing_field_is_invalid_rather_than_defaulted() -> None:
    payload = _well_formed_payload()
    del payload["original_deadline"]

    graded = graded_recovery_payload(loaded=payload)

    assert graded.payload is None
    assert graded.diagnostic == DIAGNOSTIC_INVALID_RECORD


def test_a_json_value_that_is_not_a_mapping_is_not_a_record() -> None:
    graded = graded_recovery_payload(loaded=["an attempt"])

    assert graded.payload is None
    assert graded.diagnostic == DIAGNOSTIC_INVALID_RECORD


def test_bytes_that_are_not_json_report_an_invalid_record(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"
    path = recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    path.parent.mkdir(parents=True)
    _ = path.write_text("{ not json", encoding="utf-8")

    read = read_recovery_record(path=path)

    assert read.payload is None
    assert read.diagnostic == DIAGNOSTIC_INVALID_RECORD


def test_an_absent_record_carries_neither_payload_nor_diagnostic(*, tmp_path: Path) -> None:
    read = read_recovery_record(
        path=recovery_record_path(recovery_store_root=tmp_path, attempt_id="attempt-absent")
    )

    assert read.payload is None
    assert read.diagnostic is None


def test_an_entry_that_is_not_a_mapping_is_no_observation_at_all(*, tmp_path: Path) -> None:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id=_ATTEMPT_ID,
            operation_id="op-dle6l3-shape",
            required_result_identity="item_status bd-ib-dle6l3 status closed",
            result_epoch=2,
            original_deadline="2026-10-20T20:00:00Z",
        ),
        opened_at=1.0,
    )
    path = recovery_record_path(recovery_store_root=store, attempt_id=_ATTEMPT_ID)
    payload = _well_formed_payload()
    payload["transitions"] = ["receipt", {"transition": TRANSITION_RECEIPT, "observed_at": 3.0}]
    write_recovery_record(path=path, payload=payload)

    read = read_recovery_record(path=path)
    assert read.payload is not None
    assert observed_transitions(payload=read.payload) == (TRANSITION_RECEIPT,)
    assert transition_instant(payload=read.payload, transition=TRANSITION_RECEIPT) == 3.0


def test_a_record_written_by_this_build_round_trips_through_json(*, tmp_path: Path) -> None:
    path = tmp_path / "recovery" / f"{_ATTEMPT_ID}.json"
    write_recovery_record(path=path, payload=_well_formed_payload())

    assert json.loads(path.read_text(encoding="utf-8")) == _well_formed_payload()

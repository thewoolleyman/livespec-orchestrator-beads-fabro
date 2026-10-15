"""Durable launch-obligation records: the two transitions and every unreadable shape."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    ATTACH_ABSENT,
    ATTACH_ALREADY_ATTACHED,
    ATTACH_ATTACHED,
    ATTACH_UNAVAILABLE,
    DIAGNOSTIC_INVALID_RECORD,
    DIAGNOSTIC_UNREADABLE_RECORD,
    DIAGNOSTIC_UNREADABLE_STORE,
    DIAGNOSTIC_UNSUPPORTED_SCHEMA,
    INTENT_ALREADY_RECORDED,
    INTENT_RECORDED,
    INTENT_UNAVAILABLE,
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
    attach_launch_target,
    obligation_record_path,
    outstanding_obligations,
    read_obligation_record,
    record_launch_intent,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

_COVERAGE: dict[str, object] = {"diagnostic": None, "state": "verified"}


def _intent(*, repository: Path, operation_id: str) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-b",
            repository=repository,
            invoker="role:dispatcher",
            scope="item:bd-ib-zejlae",
        ),
        required_result_identity="pull_request_state #2700 state MERGED",
        result_epoch=3,
        original_deadline="2026-10-15T06:00:00Z",
    )


def _expired_budget() -> LockBudget:
    """A budget already spent, so a contended lock is refused without sleeping."""
    return LockBudget(deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None)


def test_a_second_intent_under_one_operation_id_leaves_the_first_alone(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    intent = _intent(repository=tmp_path, operation_id="op-records-1")
    assert (
        record_launch_intent(
            intent=intent, coverage=_COVERAGE, obligation_store_root=store, recorded_at=10.0
        )
        == INTENT_RECORDED
    )

    assert (
        record_launch_intent(
            intent=intent, coverage=_COVERAGE, obligation_store_root=store, recorded_at=99.0
        )
        == INTENT_ALREADY_RECORDED
    )

    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-records-1")
    ).payload
    assert payload is not None
    assert payload["intent_recorded_at"] == 10.0
    assert payload["coverage"] == _COVERAGE
    assert payload["required_result_identity"] == "pull_request_state #2700 state MERGED"


def test_an_attachment_is_written_once_and_never_retargeted(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    _ = record_launch_intent(
        intent=_intent(repository=tmp_path, operation_id="op-records-2"),
        coverage=_COVERAGE,
        obligation_store_root=store,
        recorded_at=10.0,
    )

    assert (
        attach_launch_target(
            obligation_store_root=store,
            operation_id="op-records-2",
            target=LaunchTarget(kind="gate", identity="gate:/g:run-1"),
            attached_at=20.0,
        )
        == ATTACH_ATTACHED
    )
    assert (
        attach_launch_target(
            obligation_store_root=store,
            operation_id="op-records-2",
            target=LaunchTarget(kind="gate", identity="gate:/g:run-2"),
            attached_at=30.0,
        )
        == ATTACH_ALREADY_ATTACHED
    )

    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-records-2")
    ).payload
    assert payload is not None
    assert payload["target"] == {"identity": "gate:/g:run-1", "kind": "gate"}
    assert payload["attached_at"] == 20.0


def test_attaching_to_an_unrecorded_operation_is_absent(*, tmp_path: Path) -> None:
    assert (
        attach_launch_target(
            obligation_store_root=tmp_path / "launch-obligations",
            operation_id="op-records-3",
            target=LaunchTarget(kind="gate", identity="gate:/g:run-3"),
            attached_at=40.0,
        )
        == ATTACH_ABSENT
    )


def test_an_unacquirable_lock_reports_unavailable_rather_than_writing(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()
    with (store / ".inventory.lock").open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            intent_status = record_launch_intent(
                intent=_intent(repository=tmp_path, operation_id="op-records-4"),
                coverage=_COVERAGE,
                obligation_store_root=store,
                recorded_at=50.0,
                lock_budget=_expired_budget(),
            )
            attach_status = attach_launch_target(
                obligation_store_root=store,
                operation_id="op-records-4",
                target=LaunchTarget(kind="gate", identity="gate:/g:run-4"),
                attached_at=60.0,
                lock_budget=_expired_budget(),
            )
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert intent_status == INTENT_UNAVAILABLE
    assert attach_status == ATTACH_UNAVAILABLE
    assert not obligation_record_path(
        obligation_store_root=store, operation_id="op-records-4"
    ).exists()


def test_every_unusable_record_shape_reports_its_own_diagnostic(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()
    sound = _intent(repository=tmp_path, operation_id="sound")
    _ = record_launch_intent(
        intent=sound, coverage=_COVERAGE, obligation_store_root=store, recorded_at=70.0
    )
    array = store / "array.json"
    _ = array.write_text("[]\n", encoding="utf-8")
    incomplete = store / "incomplete.json"
    _ = incomplete.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    newer = store / "newer.json"
    _ = newer.write_text(json.dumps({"schema_version": 2}) + "\n", encoding="utf-8")
    broken = store / "broken.json"
    _ = broken.write_text("{\n", encoding="utf-8")
    directory = store / "directory.json"
    directory.mkdir()

    assert read_obligation_record(path=array).diagnostic == DIAGNOSTIC_INVALID_RECORD
    assert read_obligation_record(path=incomplete).diagnostic == DIAGNOSTIC_INVALID_RECORD
    assert read_obligation_record(path=newer).diagnostic == DIAGNOSTIC_UNSUPPORTED_SCHEMA
    assert read_obligation_record(path=broken).diagnostic == DIAGNOSTIC_INVALID_RECORD
    assert read_obligation_record(path=directory).diagnostic == DIAGNOSTIC_UNREADABLE_RECORD
    absent = read_obligation_record(path=store / "absent.json")
    assert absent.payload is None
    assert absent.diagnostic is None


def test_a_boolean_epoch_is_invalid_rather_than_an_integer(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()
    path = store / "bool-epoch.json"
    _ = path.write_text(
        json.dumps(
            {
                "attached_at": None,
                "authority": {},
                "coverage": {},
                "intent_recorded_at": 1.0,
                "operation_id": "bool-epoch",
                "original_deadline": "2026-10-15T06:00:00Z",
                "required_result_identity": "item_status x status closed",
                "result_epoch": True,
                "schema_version": 1,
                "target": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_obligation_record(path=path).diagnostic == DIAGNOSTIC_INVALID_RECORD


def test_the_census_reads_sound_records_and_names_the_rest(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    for index in (1, 2):
        _ = record_launch_intent(
            intent=_intent(repository=tmp_path, operation_id=f"op-census-{index}"),
            coverage=_COVERAGE,
            obligation_store_root=store,
            recorded_at=float(index),
        )
    _ = (store / "corrupt.json").write_text("{\n", encoding="utf-8")

    census = outstanding_obligations(obligation_store_root=store)

    assert [record["operation_id"] for record in census.records] == [
        "op-census-1",
        "op-census-2",
    ]
    assert census.diagnostics == (DIAGNOSTIC_INVALID_RECORD,)


def test_an_unlistable_store_is_unobservable_rather_than_an_empty_census(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()

    def refuse(_self: Path, _pattern: str) -> list[Path]:
        raise OSError("store unreadable")

    monkeypatch.setattr(Path, "glob", refuse)

    census = outstanding_obligations(obligation_store_root=store)

    assert census.records == ()
    assert census.diagnostics == (DIAGNOSTIC_UNREADABLE_STORE,)

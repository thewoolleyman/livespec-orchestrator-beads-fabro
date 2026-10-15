"""Reconciliation arms a sound store cannot reach: a malformed target and a held lock."""

from __future__ import annotations

import fcntl
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_obligation_reconcile import (
    RECONCILE_ATTACHMENT_UNAVAILABLE,
    RECONCILE_EFFECT_UNOBSERVABLE,
    reconcile_launch_attachment,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    INTENT_RECORDED,
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
    obligation_record_path,
    read_obligation_record,
    record_launch_intent,
    write_obligation_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

_COVERAGE: dict[str, object] = {"diagnostic": None, "state": "verified"}


class _Reader:
    def __init__(self, *, target: LaunchTarget | None) -> None:
        self.target = target
        self.observed: list[str] = []

    def observe(self, *, operation_id: str) -> LaunchTarget | None:
        self.observed.append(operation_id)
        return self.target


def _intent(*, repository: Path, operation_id: str) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-c",
            repository=repository,
            invoker="role:delegate",
            scope="item:bd-ib-zejlae",
        ),
        required_result_identity="item_comment bd-ib-zejlae marker 'done'",
        result_epoch=11,
        original_deadline="2026-10-15T07:00:00Z",
    )


def test_a_malformed_target_is_re_observed_rather_than_reported_as_attached(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    assert (
        record_launch_intent(
            intent=_intent(repository=tmp_path, operation_id="op-safety-1"),
            coverage=_COVERAGE,
            obligation_store_root=store,
            recorded_at=10.0,
        )
        == INTENT_RECORDED
    )
    path = obligation_record_path(obligation_store_root=store, operation_id="op-safety-1")
    payload = read_obligation_record(path=path).payload
    assert payload is not None
    payload["target"] = {"identity": 7, "kind": "gate"}
    write_obligation_record(path=path, payload=payload)
    reader = _Reader(target=None)

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-safety-1",
        reader=reader,
        observed_at=20.0,
    )

    assert outcome.state == RECONCILE_EFFECT_UNOBSERVABLE
    assert reader.observed == ["op-safety-1"]
    assert outcome.result_epoch == 11


def test_a_non_mapping_target_is_also_re_observed(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    _ = record_launch_intent(
        intent=_intent(repository=tmp_path, operation_id="op-safety-2"),
        coverage=_COVERAGE,
        obligation_store_root=store,
        recorded_at=10.0,
    )
    path = obligation_record_path(obligation_store_root=store, operation_id="op-safety-2")
    payload = read_obligation_record(path=path).payload
    assert payload is not None
    payload["target"] = "gate:/g:run-2"
    write_obligation_record(path=path, payload=payload)
    reader = _Reader(target=None)

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-safety-2",
        reader=reader,
        observed_at=20.0,
    )

    assert outcome.state == RECONCILE_EFFECT_UNOBSERVABLE
    assert reader.observed == ["op-safety-2"]


def test_an_unwritable_attachment_is_reported_rather_than_claimed(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    _ = record_launch_intent(
        intent=_intent(repository=tmp_path, operation_id="op-safety-3"),
        coverage=_COVERAGE,
        obligation_store_root=store,
        recorded_at=10.0,
    )
    path = obligation_record_path(obligation_store_root=store, operation_id="op-safety-3")
    reader = _Reader(target=LaunchTarget(kind="gate", identity="gate:/g:run-3"))

    budget = LockBudget(deadline=0.0, monotonic=lambda: 1.0, sleeper=lambda **_: None)

    # The store lock is held on a second descriptor throughout, and the budget
    # is already spent, so the attachment write is refused without blocking.
    with (store / ".inventory.lock").open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            outcome = reconcile_launch_attachment(
                obligation_store_root=store,
                operation_id="op-safety-3",
                reader=reader,
                observed_at=30.0,
                lock_budget=budget,
            )
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert outcome.state == RECONCILE_ATTACHMENT_UNAVAILABLE
    assert outcome.target is None
    assert outcome.result_epoch == 11
    assert reader.observed == ["op-safety-3"]
    payload = read_obligation_record(path=path).payload
    assert payload is not None
    assert payload["target"] is None

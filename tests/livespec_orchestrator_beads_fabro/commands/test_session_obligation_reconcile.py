"""A crash between launch intent and target attachment reconciles by operation id."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_obligation_reconcile import (
    RECONCILE_ALREADY_ATTACHED,
    RECONCILE_ATTACHED,
    RECONCILE_EFFECT_UNOBSERVABLE,
    RECONCILE_NO_INTENT,
    RECONCILE_OBLIGATION_UNOBSERVABLE,
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
)

_COVERAGE: dict[str, object] = {"diagnostic": None, "state": "verified"}


class _EffectReader:
    """A reader that offers a kill verb the reconciliation must never reach.

    `terminate` exists ONLY so the test can prove it stays unused. A double
    offering nothing but `observe` would make "never auto-kill a launched
    target during bookkeeping recovery" true by the double's own shape rather
    than by the reconciliation's behavior.
    """

    def __init__(self, *, target: LaunchTarget | None) -> None:
        self.target = target
        self.observed: list[str] = []
        self.terminated: list[str] = []

    def observe(self, *, operation_id: str) -> LaunchTarget | None:
        self.observed.append(operation_id)
        return self.target

    def terminate(self, *, operation_id: str) -> None:
        self.terminated.append(operation_id)


def _intent(*, repository: Path, operation_id: str) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-a",
            repository=repository,
            invoker="role:planner",
            scope="plan:agent-session-stall-prevention",
        ),
        required_result_identity="item_status bd-ib-zejlae status closed",
        result_epoch=7,
        original_deadline="2026-10-15T04:00:00Z",
    )


def test_the_reader_double_can_record_a_kill_it_is_never_asked_to_perform() -> None:
    """The positive control for every `terminated == []` assertion below.

    Without it, a double whose kill verb silently did nothing would satisfy
    those assertions whatever the reconciliation did.
    """
    reader = _EffectReader(target=None)

    reader.terminate(operation_id="op-control")

    assert reader.terminated == ["op-control"]


def test_partial_launch_attaches_by_stable_operation_id_without_duplicating(
    *, tmp_path: Path
) -> None:
    store = tmp_path / "launch-obligations"
    intent = _intent(repository=tmp_path, operation_id="op-stable-1")
    assert (
        record_launch_intent(
            intent=intent,
            coverage=_COVERAGE,
            obligation_store_root=store,
            recorded_at=100.0,
        )
        == INTENT_RECORDED
    )
    reader = _EffectReader(target=LaunchTarget(kind="gate", identity="gate:/tmp/gates:run-9"))

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-1",
        reader=reader,
        observed_at=140.0,
    )

    assert outcome.state == RECONCILE_ATTACHED
    assert outcome.target == LaunchTarget(kind="gate", identity="gate:/tmp/gates:run-9")
    assert outcome.result_epoch == 7
    assert outcome.original_deadline == "2026-10-15T04:00:00Z"
    assert reader.observed == ["op-stable-1"]
    assert reader.terminated == []
    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-stable-1")
    ).payload
    assert payload is not None
    assert payload["target"] == {"identity": "gate:/tmp/gates:run-9", "kind": "gate"}
    assert payload["attached_at"] == 140.0
    assert payload["result_epoch"] == 7
    assert payload["original_deadline"] == "2026-10-15T04:00:00Z"
    assert payload["authority"] == {
        "invoker": "role:planner",
        "repository": str(tmp_path),
        "scope": "plan:agent-session-stall-prevention",
        "session_id": "session-a",
    }


def test_reconciling_an_attached_obligation_is_idempotent(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    _ = record_launch_intent(
        intent=_intent(repository=tmp_path, operation_id="op-stable-2"),
        coverage=_COVERAGE,
        obligation_store_root=store,
        recorded_at=100.0,
    )
    target = LaunchTarget(kind="fabro-run", identity="fabro-run:01M4YT29J8")
    first_reader = _EffectReader(target=target)
    _ = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-2",
        reader=first_reader,
        observed_at=150.0,
    )
    second_reader = _EffectReader(target=LaunchTarget(kind="fabro-run", identity="other-run"))

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-2",
        reader=second_reader,
        observed_at=900.0,
    )

    assert outcome.state == RECONCILE_ALREADY_ATTACHED
    assert outcome.target == target
    assert outcome.result_epoch == 7
    assert second_reader.observed == []
    assert second_reader.terminated == []
    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-stable-2")
    ).payload
    assert payload is not None
    assert payload["attached_at"] == 150.0
    assert payload["target"] == {"identity": "fabro-run:01M4YT29J8", "kind": "fabro-run"}


def test_an_unobservable_effect_retains_uncertainty(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    _ = record_launch_intent(
        intent=_intent(repository=tmp_path, operation_id="op-stable-3"),
        coverage=_COVERAGE,
        obligation_store_root=store,
        recorded_at=100.0,
    )
    reader = _EffectReader(target=None)

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-3",
        reader=reader,
        observed_at=160.0,
    )

    assert outcome.state == RECONCILE_EFFECT_UNOBSERVABLE
    assert outcome.target is None
    assert outcome.result_epoch == 7
    assert reader.terminated == []
    payload = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id="op-stable-3")
    ).payload
    assert payload is not None
    assert payload["target"] is None
    assert payload["attached_at"] is None


def test_an_unreadable_obligation_is_unobservable_rather_than_absent(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()
    path = obligation_record_path(obligation_store_root=store, operation_id="op-stable-4")
    _ = path.write_text("{not json\n", encoding="utf-8")
    reader = _EffectReader(target=LaunchTarget(kind="gate", identity="gate:/tmp/gates:run-4"))

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-4",
        reader=reader,
        observed_at=170.0,
    )

    assert outcome.state == RECONCILE_OBLIGATION_UNOBSERVABLE
    assert outcome.result_epoch is None
    assert outcome.original_deadline is None
    assert reader.observed == []


def test_no_intent_record_means_nothing_was_launched_under_that_identity(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    reader = _EffectReader(target=LaunchTarget(kind="gate", identity="gate:/tmp/gates:run-5"))

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-5",
        reader=reader,
        observed_at=180.0,
    )

    assert outcome.state == RECONCILE_NO_INTENT
    assert outcome.target is None
    assert reader.observed == []
    assert reader.terminated == []


def test_an_unsupported_schema_is_unobservable(*, tmp_path: Path) -> None:
    store = tmp_path / "launch-obligations"
    store.mkdir()
    path = obligation_record_path(obligation_store_root=store, operation_id="op-stable-6")
    _ = path.write_text(json.dumps({"schema_version": 99}) + "\n", encoding="utf-8")
    reader = _EffectReader(target=None)

    outcome = reconcile_launch_attachment(
        obligation_store_root=store,
        operation_id="op-stable-6",
        reader=reader,
        observed_at=190.0,
    )

    assert outcome.state == RECONCILE_OBLIGATION_UNOBSERVABLE
    assert reader.observed == []

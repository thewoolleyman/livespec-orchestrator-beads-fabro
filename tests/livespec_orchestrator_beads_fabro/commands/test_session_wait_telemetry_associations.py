"""Work associations ride the wait's record, so later events name them honestly.

A wait is armed by a process that knows its work item, dispatch and run, but
receipt is acknowledged and inventory is read by DIFFERENT processes whose
environment says nothing about that wait. The associations are therefore
persisted when the wait is armed and read back from its record: an event for a
wait that never knew them carries none (they are never invented), and an
inventory caller's own environment is never stamped onto someone else's wait.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import SessionEvent
from livespec_orchestrator_beads_fabro.commands._session_telemetry_gate import load_gate
from livespec_orchestrator_beads_fabro.commands._session_wait_telemetry import (
    Associations,
    SessionWaitPublisher,
    associations_from_environ,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
    InventoryRecord,
    InventorySnapshot,
)

_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_ASSOCIATIONS = {
    "LIVESPEC_WORK_ITEM_ID": "bd-ib-4mcuty",
    "LIVESPEC_DISPATCH_ID": "d6f52987d4e9444aa88d096c09244075",
    "LIVESPEC_FABRO_RUN_ID": "01M64HM1QPMC5P5TWR5SWD9XJR",
}
_ASSOCIATION_KEYS = {"work.item.id", "livespec.dispatch.id", "fabro.run_id"}


@pytest.fixture(autouse=True)
def hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (_ENDPOINT_ENV, "TRACEPARENT", *_ASSOCIATIONS):
        monkeypatch.delenv(name, raising=False)


@dataclass(kw_only=True)
class _Sink:
    exporting: bool = True
    events: list[SessionEvent] = field(default_factory=list)

    def emit(self, *, event: SessionEvent) -> None:
        self.events.append(event)


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True

    def keys_by_name(self) -> list[tuple[str, set[str]]]:
        return [
            (
                cast("str", span["name"]),
                {
                    cast("str", entry["key"])
                    for entry in cast("list[dict[str, object]]", span["attributes"])
                },
            )
            for spans, _ in self.calls
            for span in spans
        ]


@contextmanager
def _receiver(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_CapturingExporter]:
    exporter = _CapturingExporter()
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=HeartbeatSink(path=tmp_path / "beats.json"),
    )
    receiver.start()
    monkeypatch.setenv(_ENDPOINT_ENV, f"http://127.0.0.1:{receiver.bound_port}")
    try:
        yield exporter
    finally:
        receiver.stop()


@dataclass(kw_only=True)
class _EndsProbe:
    target: WaitTarget

    def poll(self, *, now: float) -> GateObservation | None:
        return GateObservation.finished(
            target=self.target, state="PASSED", exit_code=0, observed_at=now
        )

    def cancel(self, *, timeout_seconds: float) -> None:
        del timeout_seconds


class _Launcher:
    def launch(self, *, target: WaitTarget, timeout_seconds: float) -> _EndsProbe:
        del timeout_seconds
        return _EndsProbe(target=target)


def _launcher(*, repository: Path) -> _Launcher:
    del repository
    return _Launcher()


def _own_root(*, repository: Path) -> Path:
    return repository


def _observe(*, target: WaitTarget, observed_at: float) -> GateObservation:
    return GateObservation.finished(
        target=target, state="PASSED", exit_code=0, observed_at=observed_at
    )


def _no_generation(*, pid: int) -> str | None:
    del pid


def _seams() -> session_wait.SessionWaitCliSeams:
    return session_wait.SessionWaitCliSeams(
        primary_repository=_own_root,
        launcher=_launcher,
        observe_target=_observe,
        process_generation=_no_generation,
        wall_clock=time.time,
    )


def _repository(*, tmp_path: Path) -> Path:
    repository = tmp_path / "project"
    run = repository / "gate-runs" / "run-1"
    run.mkdir(parents=True)
    _ = (run / "started_at").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")
    return repository


def _arm(*, repository: Path) -> int:
    return session_wait.main(
        argv=[
            "wait",
            "--repo",
            str(repository),
            "--session-id",
            "session-1",
            "--wait-id",
            "wait-1",
            "--deadline-seconds",
            "30",
            "--gate",
            "run-1",
        ],
        seams=_seams(),
    )


def test_associations_are_recorded_at_arming_and_named_by_later_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        for name, value in _ASSOCIATIONS.items():
            monkeypatch.setenv(name, value)
        assert _arm(repository=repository) == 0
        for name in _ASSOCIATIONS:
            monkeypatch.delenv(name)
        armed = len(exporter.keys_by_name())
        ack = ["ack", "--repo", str(repository), "--session-id", "session-1", "--wait-id", "wait-1"]
        _ = session_wait.main(argv=ack, seams=_seams())
        _ = session_wait.main(argv=["inventory", "--repo", str(repository)], seams=_seams())

    recorded = json.loads((repository / "session-waits" / "wait-1.json").read_text("utf-8"))
    assert recorded["associations"] == {
        "fabro.run_id": _ASSOCIATIONS["LIVESPEC_FABRO_RUN_ID"],
        "livespec.dispatch.id": _ASSOCIATIONS["LIVESPEC_DISPATCH_ID"],
        "work.item.id": _ASSOCIATIONS["LIVESPEC_WORK_ITEM_ID"],
    }
    later = exporter.keys_by_name()[armed:]
    assert [name for name, _ in later] == [
        "session.wait.acknowledged",
        "session.wait.inventory",
        "session.wait.observed",
    ]
    assert later[0][1] >= _ASSOCIATION_KEYS
    assert _ASSOCIATION_KEYS.isdisjoint(later[1][1])
    assert later[2][1] >= _ASSOCIATION_KEYS


def test_a_record_written_before_associations_existed_publishes_without_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        assert _arm(repository=repository) == 0
        record = repository / "session-waits" / "wait-1.json"
        payload = json.loads(record.read_text("utf-8"))
        del payload["associations"]
        _ = record.write_text(json.dumps(payload), encoding="utf-8")
        armed = len(exporter.keys_by_name())
        ack = ["ack", "--repo", str(repository), "--session-id", "session-1", "--wait-id", "wait-1"]
        _ = session_wait.main(argv=ack, seams=_seams())

    acknowledged = exporter.keys_by_name()[armed:]
    assert [name for name, _ in acknowledged] == ["session.wait.acknowledged"]
    assert _ASSOCIATION_KEYS.isdisjoint(acknowledged[0][1])


def test_associations_are_read_only_from_identifier_shaped_environment_values() -> None:
    environ = {
        "LIVESPEC_WORK_ITEM_ID": "bd-ib-4mcuty",
        "LIVESPEC_DISPATCH_ID": "not an identifier!",
        "LIVESPEC_FABRO_RUN_ID": "  ",
    }

    assert associations_from_environ(environ=environ) == Associations(work_item_id="bd-ib-4mcuty")
    assert associations_from_environ(environ={}) == Associations()


def _snapshot(*, records: tuple[InventoryRecord, ...], at: float) -> InventorySnapshot:
    return InventorySnapshot(observation_id="snapshot", observed_at=at, records=records)


def _broken(*, wait_id: str) -> InventoryRecord:
    return InventoryRecord(
        wait_id=wait_id,
        record_state="unavailable",
        diagnostic="invalid-record",
        findings=frozenset({"invalid-record"}),
        observations=(),
        observation_sequence=0,
    )


def test_a_sink_that_is_not_exporting_consumes_no_gate_state(tmp_path: Path) -> None:
    sink = _Sink(exporting=False)
    gate_path = tmp_path / "state"
    publisher = SessionWaitPublisher(sink=sink, gate_path=gate_path)

    publisher.inventory(snapshot=_snapshot(records=(), at=100.0))

    assert sink.events == []
    assert not gate_path.exists()


def test_an_unchanged_unavailable_record_is_not_republished_within_the_minute(
    tmp_path: Path,
) -> None:
    sink = _Sink()
    publisher = SessionWaitPublisher(sink=sink, gate_path=tmp_path / "state")
    records = (_broken(wait_id="broken"),)

    publisher.inventory(snapshot=_snapshot(records=records, at=100.0))
    first = len(sink.events)
    publisher.inventory(snapshot=_snapshot(records=records, at=130.0))
    unchanged = len(sink.events)
    publisher.inventory(snapshot=_snapshot(records=(*records, _broken(wait_id="other")), at=131.0))

    assert first == 2
    assert unchanged == first
    assert [(event.name, event.attributes.get("session.wait.id")) for event in sink.events[2:]] == [
        ("session.wait.inventory", None),
        ("session.wait.observed", "other"),
    ]


def test_without_a_gate_file_every_snapshot_is_published(tmp_path: Path) -> None:
    sink = _Sink()
    publisher = SessionWaitPublisher(sink=sink)

    publisher.inventory(snapshot=_snapshot(records=(), at=100.0))
    publisher.inventory(snapshot=_snapshot(records=(), at=101.0))

    assert [event.name for event in sink.events] == ["session.wait.inventory"] * 2
    assert not list(tmp_path.iterdir())


def test_the_gate_ignores_marks_with_a_non_numeric_instant(tmp_path: Path) -> None:
    path = tmp_path / "state"
    _ = path.write_text(json.dumps({"a": ["s", "text"], "b": ["s", 5]}), encoding="utf-8")

    assert load_gate(path=path).marks == {"b": ("s", 5.0)}

"""Wait lifecycle and inventory reach the host-local receiver as typed events.

Scenario 159 of `SPECIFICATION/scenarios.md` asks that arming, observation
changes, return, inventory and receipt acknowledgement arrive as identity-linked
events with typed numeric measurements, that an empty inventory publishes an
explicit zero-count summary, that unchanged observations are exported at most
once a minute, and that export trouble never moves a wait's deadline. Every
case drives the public `session_wait.main` over a REAL localhost
`OtelReceiver` (the positive control, and the only way to see an attribute the
receiver allowlist would silently drop) or a listener that never answers (the
blocked-exporter control).
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _session_wait_cli, session_wait
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import (
    DegradationReport,
    SessionTelemetry,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_gate import (
    ObservationGate,
    load_gate,
    save_gate,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)

_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_ASSOCIATION_ENV = {
    "LIVESPEC_WORK_ITEM_ID": "bd-ib-4mcuty",
    "LIVESPEC_DISPATCH_ID": "d6f52987d4e9444aa88d096c09244075",
    "LIVESPEC_FABRO_RUN_ID": "01M64HM1QPMC5P5TWR5SWD9XJR",
}
_AMBIENT_ENV = (_ENDPOINT_ENV, "TRACEPARENT", *_ASSOCIATION_ENV)

Decoded = dict[str, object]


def _no_sleep(seconds: float) -> None:
    del seconds


@pytest.fixture(autouse=True)
def hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(time, "sleep", _no_sleep)


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True

    def events(self) -> list[tuple[str, Decoded, str]]:
        return [
            (cast("str", span["name"]), _decode(span=span), cast("str", span["traceId"]))
            for spans, _ in self.calls
            for span in spans
        ]


def _decode(*, span: dict[str, object]) -> Decoded:
    decoded: Decoded = {}
    for entry in cast("list[dict[str, object]]", span["attributes"]):
        value = cast("dict[str, object]", entry["value"])
        key = cast("str", entry["key"])
        if "intValue" in value:
            decoded[key] = int(cast("str", value["intValue"]))
        elif "doubleValue" in value:
            decoded[key] = float(cast("float", value["doubleValue"]))
        elif "boolValue" in value:
            decoded[key] = bool(value["boolValue"])
        elif "arrayValue" in value:
            items = cast("dict[str, list[dict[str, str]]]", value["arrayValue"])["values"]
            decoded[key] = [item["stringValue"] for item in items]
        else:
            decoded[key] = value["stringValue"]
    return decoded


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
class _ScriptedProbe:
    states: list[GateObservation]

    def poll(self, *, now: float) -> GateObservation | None:
        observation = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return replace(observation, observed_at=now)

    def cancel(self, *, timeout_seconds: float) -> None:
        del timeout_seconds


@dataclass(kw_only=True)
class _ScriptedLauncher:
    script: Callable[[WaitTarget], list[GateObservation]]

    def launch(self, *, target: WaitTarget, timeout_seconds: float) -> _ScriptedProbe:
        del timeout_seconds
        return _ScriptedProbe(states=self.script(target))


def _ends_after_two_running_polls(target: WaitTarget) -> list[GateObservation]:
    running = GateObservation.running(target=target, observed_at=0.0)
    return [
        running,
        running,
        GateObservation.finished(target=target, state="FAILED", exit_code=23, observed_at=0.0),
    ]


def _never_ends(target: WaitTarget) -> list[GateObservation]:
    return [GateObservation.running(target=target, observed_at=0.0)]


def _own_root(*, repository: Path) -> Path:
    return repository


@dataclass(kw_only=True)
class _Clock:
    now: float = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now


def _launcher_factory(
    *, script: Callable[[WaitTarget], list[GateObservation]]
) -> Callable[..., _ScriptedLauncher]:
    def factory(*, repository: Path) -> _ScriptedLauncher:
        del repository
        return _ScriptedLauncher(script=script)

    return factory


def _seams(
    *,
    script: Callable[[WaitTarget], list[GateObservation]] = _ends_after_two_running_polls,
    clock: Callable[[], float] = time.time,
    waiter_alive: bool = True,
) -> session_wait.SessionWaitCliSeams:
    def observe(*, target: WaitTarget, observed_at: float) -> GateObservation:
        return GateObservation.finished(
            target=target, state="FAILED", exit_code=23, observed_at=observed_at
        )

    def generation(*, pid: int) -> str | None:
        del pid
        return "gen" if waiter_alive else None

    return session_wait.SessionWaitCliSeams(
        primary_repository=_own_root,
        launcher=_launcher_factory(script=script),
        observe_target=observe,
        process_generation=generation,
        wall_clock=clock,
    )


def _repository(*, tmp_path: Path) -> Path:
    repository = tmp_path / "project"
    run = repository / "gate-runs" / "run-1"
    run.mkdir(parents=True)
    _ = (run / "started_at").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")
    return repository


def _wait_argv(*, repository: Path, wait_id: str = "wait-1", deadline: float = 30.0) -> list[str]:
    return [
        "wait",
        "--repo",
        str(repository),
        "--session-id",
        "session-1",
        "--wait-id",
        wait_id,
        "--deadline-seconds",
        str(deadline),
        "--gate",
        "run-1",
    ]


def _names(*, exporter: _CapturingExporter) -> list[str]:
    return [name for name, _, _ in exporter.events()]


def test_arming_observation_changes_and_return_publish_typed_identity_linked_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    for name, value in _ASSOCIATION_ENV.items():
        monkeypatch.setenv(name, value)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        code = session_wait.main(argv=_wait_argv(repository=repository), seams=_seams())

    assert code == 0
    assert _names(exporter=exporter) == [
        "session.wait.armed",
        "session.wait.observed",
        "session.wait.observed",
        "session.wait.returned",
    ]
    armed, running, failed, returned = (attrs for _, attrs, _ in exporter.events())
    assert {armed["session.wait.id"], running["session.wait.id"], returned["session.wait.id"]} == {
        "wait-1"
    }
    assert armed["session.repository"] == "project"
    assert armed["session.id"] == "session-1"
    assert armed["work.item.id"] == "bd-ib-4mcuty"
    assert armed["livespec.dispatch.id"] == _ASSOCIATION_ENV["LIVESPEC_DISPATCH_ID"]
    assert armed["fabro.run_id"] == _ASSOCIATION_ENV["LIVESPEC_FABRO_RUN_ID"]
    assert armed["session.wait.budget_seconds"] == 30.0
    assert armed["session.wait.target_count"] == 1
    assert armed["session.wait.target.kind"] == "gate"
    assert len(cast("str", armed["session.wait.target.id"])) == 16
    assert running["session.observation.state"] == "RUNNING"
    assert running["session.observation.sequence"] == 1
    assert failed["session.observation.state"] == "FAILED"
    assert failed["session.observation.sequence"] == 3
    assert isinstance(failed["session.observation.age_seconds"], float)
    assert returned["session.wait.return_reason"] == "target-ended"
    assert returned["session.wait.trigger_exit_code"] == 23
    assert isinstance(returned["session.wait.elapsed_seconds"], float)
    assert 0.0 <= cast("float", returned["session.wait.remaining_seconds"]) <= 30.0
    assert returned["session.wait.budget_seconds"] == 30.0
    assert len({trace for _, _, trace in exporter.events()}) == 1
    leaked = [
        value
        for _, attrs, _ in exporter.events()
        for value in attrs.values()
        if isinstance(value, str) and str(tmp_path) in value
    ]
    assert leaked == []


def test_unknown_work_associations_are_not_invented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        _ = session_wait.main(argv=_wait_argv(repository=repository), seams=_seams())

    assert _names(exporter=exporter)[:1] == ["session.wait.armed"]
    armed = exporter.events()[0][1]
    assert armed["session.wait.id"] == "wait-1"
    assert {"work.item.id", "livespec.dispatch.id", "fabro.run_id"}.isdisjoint(armed)


def test_acknowledgement_is_receipt_only_and_joins_the_wait_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    ack = ["--repo", str(repository), "--wait-id", "wait-1"]
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        _ = session_wait.main(argv=_wait_argv(repository=repository), seams=_seams())
        before = len(exporter.events())
        refused = session_wait.main(
            argv=["ack", *ack, "--session-id", "someone-else"], seams=_seams()
        )
        assert len(exporter.events()) == before
        accepted = session_wait.main(
            argv=["ack", *ack, "--session-id", "session-1"], seams=_seams()
        )

    assert (refused, accepted) == (1, 0)
    assert _names(exporter=exporter)[-1:] == ["session.wait.acknowledged"]
    name, attrs, trace = exporter.events()[-1]
    assert name == "session.wait.acknowledged"
    assert attrs["session.wait.acknowledged"] is True
    assert attrs["session.wait.return_reason"] == "target-ended"
    assert attrs["session.wait.id"] == "wait-1"
    assert trace == exporter.events()[0][2]


def test_an_empty_inventory_publishes_a_timestamped_zero_count_summary_once_a_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    clock = _Clock()
    argv = ["inventory", "--repo", str(repository)]
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        _ = session_wait.main(argv=argv, seams=_seams(clock=clock))
        clock.now += 10.0
        _ = session_wait.main(argv=argv, seams=_seams(clock=clock))
        clock.now += 61.0
        _ = session_wait.main(argv=argv, seams=_seams(clock=clock))

    events = exporter.events()
    assert _names(exporter=exporter) == ["session.wait.inventory", "session.wait.inventory"]
    first, third = events[0][1], events[1][1]
    assert first["session.inventory.wait_count"] == 0
    assert first["session.inventory.active_count"] == 0
    assert first["session.inventory.unacknowledged_count"] == 0
    assert first["session.observation.time"] == "2023-11-14T22:13:20Z"
    assert first["session.observation.id"] != third["session.observation.id"]
    assert third["session.observation.time"] == "2023-11-14T22:14:31Z"
    assert "session.observation.unavailable" not in first


def test_inventory_publishes_per_wait_observations_that_stay_distinct_per_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    clock = _Clock()
    argv = ["inventory", "--repo", str(repository)]
    seams = _seams(clock=clock, waiter_alive=False)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        _ = session_wait.main(argv=_wait_argv(repository=repository), seams=_seams())
        armed_events = len(exporter.events())
        _ = session_wait.main(argv=argv, seams=seams)
        first = exporter.events()[armed_events:]
        clock.now += 10.0
        _ = session_wait.main(argv=argv, seams=seams)
        unchanged = exporter.events()[armed_events + len(first) :]
        clock.now += 61.0
        _ = session_wait.main(argv=argv, seams=seams)
        later = exporter.events()[armed_events + len(first) :]

    assert [name for name, _, _ in first] == ["session.wait.inventory", "session.wait.observed"]
    summary, observed = first[0][1], first[1][1]
    assert summary["session.inventory.wait_count"] == 1
    assert summary["session.inventory.active_count"] == 0
    assert summary["session.inventory.unacknowledged_count"] == 1
    assert observed["session.wait.id"] == "wait-1"
    assert observed["session.observation.state"] == "FAILED"
    assert observed["session.wait.waiter_alive"] is False
    assert observed["session.wait.acknowledged"] is False
    assert observed["session.observation.id"] == summary["session.observation.id"]
    assert unchanged == []
    assert [name for name, _, _ in later] == ["session.wait.inventory", "session.wait.observed"]
    assert later[1][1]["session.wait.id"] == "wait-1"
    assert later[1][1]["session.observation.id"] != observed["session.observation.id"]


def test_an_unreadable_record_is_published_as_unavailable_never_as_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    store = repository / "session-waits"
    store.mkdir()
    _ = (store / "broken.json").write_text("{not json", encoding="utf-8")
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        _ = session_wait.main(argv=["inventory", "--repo", str(repository)], seams=_seams())

    assert _names(exporter=exporter) == ["session.wait.inventory", "session.wait.observed"]
    summary, observed = exporter.events()[0][1], exporter.events()[1][1]
    assert summary["session.inventory.wait_count"] == 1
    assert summary["session.observation.unavailable"] == ["wait_record"]
    assert observed["session.wait.id"] == "broken"
    assert observed["session.observation.state"] == "unavailable"
    assert observed["session.observation.unavailable"] == ["invalid-record"]


@contextmanager
def _hanging_listener() -> Iterator[int]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    try:
        yield int(listener.getsockname()[1])
    finally:
        listener.close()


def test_a_blocked_exporter_leaves_the_wait_result_on_its_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The result is written before the exporter's shutdown allowance is spent.

    The bound is an ORDERING rather than a stopwatch reading: the wait's result
    must reach stdout BEFORE the blocked exporter is closed, so the bounded
    shutdown can never sit on the deadline path however slowly a loaded host
    runs either step. The exporter really is blocked: its receiver accepts and
    never answers.
    """
    repository = _repository(tmp_path=tmp_path)
    order: list[str] = []
    original_write = _session_wait_cli.write_stdout
    original_close = SessionTelemetry.close

    def recording_write(*, text: str) -> None:
        order.append("result-written")
        _ = original_write(text=text)

    def recording_close(self: SessionTelemetry) -> DegradationReport:
        order.append("exporter-closed")
        return original_close(self)

    with _hanging_listener() as port:
        monkeypatch.setattr(_session_wait_cli, "write_stdout", recording_write)
        monkeypatch.setattr(SessionTelemetry, "close", recording_close)
        monkeypatch.setenv(_ENDPOINT_ENV, f"http://127.0.0.1:{port}")
        code = session_wait.main(
            argv=_wait_argv(repository=repository, deadline=1.0),
            seams=_seams(script=_never_ends),
        )

    assert code == 0
    assert '"command_outcome": "deadline"' in capsys.readouterr().out
    assert order.count("exporter-closed") == 1
    assert order[-1] == "exporter-closed"
    assert "result-written" in order[:-1]


def test_a_blocked_exporter_is_reported_locally_and_an_unset_one_says_local_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = _repository(tmp_path=tmp_path)
    argv = ["inventory", "--repo", str(repository)]
    code = session_wait.main(argv=argv, seams=_seams())
    local_only = capsys.readouterr()

    with _hanging_listener() as port:
        monkeypatch.setenv(_ENDPOINT_ENV, f"http://127.0.0.1:{port}")
        degraded_code = session_wait.main(argv=argv, seams=_seams())
    degraded = capsys.readouterr()

    assert (code, degraded_code) == (0, 0)
    assert "session telemetry local-only" in local_only.err
    assert "session telemetry degraded" in degraded.err
    assert '"records": []' in local_only.out
    assert '"records": []' in degraded.out


def test_unchanged_observations_are_admitted_at_most_once_a_minute() -> None:
    gate = ObservationGate()

    assert gate.admit(key="w\0t", signature="RUNNING", now=100.0)
    assert not gate.admit(key="w\0t", signature="RUNNING", now=159.9)
    assert gate.admit(key="w\0t", signature="FAILED", now=160.0)
    assert gate.admit(key="w\0t", signature="FAILED", now=220.0)
    assert gate.admit(key="w\0other", signature="FAILED", now=221.0)
    assert gate.admit(key="w\0t", signature="FAILED", now=100.0)


def test_the_gate_survives_between_invocations_and_forgives_a_damaged_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state"
    gate = ObservationGate()
    assert gate.admit(key="a", signature="x", now=1000.0)
    assert gate.admit(key="old", signature="x", now=1.0)
    save_gate(path=path, gate=gate, now=1010.0)

    reloaded = load_gate(path=path)

    assert not reloaded.admit(key="a", signature="x", now=1020.0)
    assert reloaded.admit(key="old", signature="x", now=1020.0)
    damaged_files = {
        "": {},
        "[1]": {},
        "{not json": {},
        '{"a": "scalar", "b": ["x"], "c": [1, 2], "d": ["s", 5]}': {"d": ("s", 5.0)},
    }
    for damaged, expected in damaged_files.items():
        _ = path.write_text(damaged, encoding="utf-8")
        assert load_gate(path=path).marks == expected
    assert load_gate(path=tmp_path / "absent").marks == {}

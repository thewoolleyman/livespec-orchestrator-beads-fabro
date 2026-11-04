"""Scenario 159 — wait inventory and measurements arrive without controlling liveness.

`SPECIFICATION/scenarios.md` Scenario 159 has two scenarios, and both are driven
here through PUBLIC surfaces over real sockets, because the claim is about what
reaches the receiving side and about what the local work still does.

LEG ONE (lifecycle and snapshots) runs the installed host CLI, `session_wait.main`,
against a real `OtelReceiver` — the shared enrich/scrub seam — so an attribute the
receiver allowlist would silently drop is a failure here rather than an
unobserved loss. One arc covers arming, observation changes, return, an empty
inventory (the explicit zero-count summary), a populated inventory, the
rate limit on unchanged observations and receipt acknowledgement; a canary secret
in the environment proves nothing but curated fields leave. LEG TWO pins the wire
contract the receiver's shape hides: resource service and namespace, and the
versioned scope.

The Outline (LEG THREE) runs a REAL recovery pass under each export condition and
asserts the local effect first: the command ran once and the attempt reached
execution whatever the exporter did, and the failure is reported locally.

What this does NOT bind is the Honeycomb destination itself. The scenario's first
Then ("arrive in Honeycomb") is declared host-captured on the work item, because
the released host pipeline and the dataset are outside any isolated proof surface.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_action import (
    AuthoritativeEvidence,
    Reading,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_consumer import (
    ConsumerRequest,
    consume_recovery_obligation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect
from livespec_orchestrator_beads_fabro.commands._session_recovery_outcome import CONSUMER_EXECUTED
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_NOTIFICATION,
    RecoveryAttempt,
    open_recovery_attempt,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import SafetyState
from livespec_orchestrator_beads_fabro.commands._session_recovery_telemetry import (
    TransitionScope,
    record_transition,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import (
    STATE_CONFIGURED,
    PostOutcome,
    SessionTelemetry,
    TelemetryConfig,
    config_from_environ,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)

from tests.integration.session_recovery_doubles import RecordingCommand, RecordingLookup

_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_CANARIES = ("sk-ant-canary-7f3a91", "hcaik_canary_5512")
_ASSOCIATIONS = {
    "LIVESPEC_WORK_ITEM_ID": "bd-ib-4mcuty",
    "LIVESPEC_DISPATCH_ID": "d6f52987d4e9444aa88d096c09244075",
    "LIVESPEC_FABRO_RUN_ID": "01M64HM1QPMC5P5TWR5SWD9XJR",
}
_FIRST_INSTANT = 1_700_000_000.0

Decoded = dict[str, object]


@pytest.fixture(autouse=True)
def hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (_ENDPOINT_ENV, "TRACEPARENT", *_ASSOCIATIONS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", _CANARIES[0])
    monkeypatch.setenv("HONEYCOMB_INGEST_KEY_LIVESPEC", _CANARIES[1])


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True

    def events(self) -> list[tuple[str, Decoded]]:
        return [(cast("str", span["name"]), _decode(span=span)) for span in self._spans()]

    def datasets(self) -> set[str]:
        return {dataset for _, dataset in self.calls}

    def _spans(self) -> list[dict[str, object]]:
        return [span for spans, _ in self.calls for span in spans]


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


class _Launcher:
    def launch(self, *, target: WaitTarget, timeout_seconds: float) -> _ScriptedProbe:
        del timeout_seconds
        return _ScriptedProbe(
            states=[
                GateObservation.running(target=target, observed_at=0.0),
                GateObservation.finished(
                    target=target, state="FAILED", exit_code=23, observed_at=0.0
                ),
            ]
        )


def _launcher(*, repository: Path) -> _Launcher:
    del repository
    return _Launcher()


def _own_root(*, repository: Path) -> Path:
    return repository


def _observe_failed(*, target: WaitTarget, observed_at: float) -> GateObservation:
    return GateObservation.finished(
        target=target, state="FAILED", exit_code=23, observed_at=observed_at
    )


def _waiter_gone(*, pid: int) -> str | None:
    del pid


@dataclass(kw_only=True)
class _Clock:
    now: float = _FIRST_INSTANT

    def __call__(self) -> float:
        return self.now


def _seams(*, clock: _Clock) -> session_wait.SessionWaitCliSeams:
    return session_wait.SessionWaitCliSeams(
        primary_repository=_own_root,
        launcher=_launcher,
        observe_target=_observe_failed,
        process_generation=_waiter_gone,
        wall_clock=clock,
    )


def _repository(*, tmp_path: Path) -> Path:
    repository = tmp_path / "project"
    run = repository / "gate-runs" / "run-1"
    run.mkdir(parents=True)
    _ = (run / "started_at").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")
    return repository


def _wait_argv(*, repository: Path, wait_id: str) -> list[str]:
    return [
        "wait", "--repo", str(repository), "--session-id", "session-159", "--wait-id", wait_id,
        "--deadline-seconds", "30", "--gate", "run-1",
    ]  # fmt: skip


def _run_arc(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Decoded]]:
    """The whole lifecycle through the host CLI, against the real receiver seam."""
    repository = _repository(tmp_path=tmp_path)
    clock = _Clock()
    inventory = ["inventory", "--repo", str(repository)]
    ack = ["ack", "--repo", str(repository), "--session-id", "session-159", "--wait-id", "wait-1"]
    seams = _seams(clock=clock)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        for name, value in _ASSOCIATIONS.items():
            monkeypatch.setenv(name, value)
        _ = session_wait.main(argv=inventory, seams=seams)
        _ = session_wait.main(argv=_wait_argv(repository=repository, wait_id="wait-1"), seams=seams)
        _ = session_wait.main(argv=inventory, seams=seams)
        clock.now += 10.0
        _ = session_wait.main(argv=inventory, seams=seams)
        _ = session_wait.main(argv=ack, seams=seams)
        _ = session_wait.main(argv=inventory, seams=seams)
        for name in _ASSOCIATIONS:
            monkeypatch.delenv(name)
        _ = session_wait.main(argv=_wait_argv(repository=repository, wait_id="wait-2"), seams=seams)
    assert exporter.datasets() == {"livespec-dispatcher"}
    return exporter.events()


def test_scenario_159_lifecycle_and_snapshots_arrive_scrubbed_typed_and_rate_limited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _run_arc(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert [name for name, _ in events] == [
        "session.wait.inventory",
        "session.wait.armed",
        "session.wait.observed",
        "session.wait.observed",
        "session.wait.returned",
        "session.wait.inventory",
        "session.wait.observed",
        "session.wait.acknowledged",
        "session.wait.inventory",
        "session.wait.observed",
        "session.wait.armed",
        "session.wait.observed",
        "session.wait.observed",
        "session.wait.returned",
    ]
    empty, armed, running, failed, returned, populated, listed, acknowledged, settled = (
        attrs for _, attrs in events[:9]
    )
    assert empty["session.inventory.wait_count"] == 0
    assert empty["session.inventory.active_count"] == 0
    assert empty["session.inventory.unacknowledged_count"] == 0
    assert empty["session.observation.time"] == "2023-11-14T22:13:20Z"
    assert armed["session.wait.budget_seconds"] == 30.0
    assert (running["session.observation.state"], failed["session.observation.state"]) == (
        "RUNNING",
        "FAILED",
    )
    assert returned["session.wait.trigger_exit_code"] == 23
    assert isinstance(returned["session.wait.elapsed_seconds"], float)
    assert populated["session.inventory.unacknowledged_count"] == 1
    assert listed["session.wait.id"] == "wait-1"
    assert listed["session.observation.id"] == populated["session.observation.id"]
    assert acknowledged["session.wait.acknowledged"] is True
    assert settled["session.inventory.unacknowledged_count"] == 0
    snapshot_ids = {a["session.observation.id"] for a in (empty, populated, settled)}
    assert len(snapshot_ids) == 3
    for _, attrs in events[1:8]:
        if "session.wait.id" in attrs:
            assert attrs["work.item.id"] == "bd-ib-4mcuty"
            assert attrs["fabro.run_id"] == _ASSOCIATIONS["LIVESPEC_FABRO_RUN_ID"]
    unknown = events[10][1]
    assert {"work.item.id", "livespec.dispatch.id", "fabro.run_id"}.isdisjoint(unknown)
    delivered = json.dumps(events)
    assert not any(canary in delivered for canary in (*_CANARIES, str(tmp_path), "gate-runs"))


def _request_complete(*, received: bytes) -> bool:
    head, separator, body = received.partition(b"\r\n\r\n")
    return bool(separator) and len(body) >= _content_length(head=head)


def _content_length(*, head: bytes) -> int:
    return int(
        next(
            line.split(b":")[1]
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length")
        )
    )


@contextmanager
def _capturing_server() -> Iterator[tuple[str, list[bytes]]]:
    bodies: list[bytes] = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            received = b""
            while not _request_complete(received=received):
                received += connection.recv(65536)
            bodies.append(received.partition(b"\r\n\r\n")[2])
            connection.sendall(
                b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\nconnection: close\r\n\r\n{}"
            )

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}", bodies
    finally:
        thread.join(timeout=5.0)
        listener.close()


def test_scenario_159_events_carry_the_service_namespace_and_versioned_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path=tmp_path)
    with _capturing_server() as (url, bodies):
        monkeypatch.setenv(_ENDPOINT_ENV, url)
        _ = session_wait.main(
            argv=["inventory", "--repo", str(repository)], seams=_seams(clock=_Clock())
        )

    assert len(bodies) == 1
    request = json.loads(bodies[0])
    resource = request["resourceSpans"][0]
    attributes = {a["key"]: a["value"]["stringValue"] for a in resource["resource"]["attributes"]}
    assert attributes == {
        "service.name": "livespec-dispatcher",
        "service.namespace": "livespec-family",
    }
    scope = resource["scopeSpans"][0]["scope"]
    assert scope["name"] == "livespec.orchestrator.session_wait"
    assert scope["version"] == "1.0.0"


def _attempt(*, store: Path) -> None:
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id="attempt-159",
            operation_id="op-159",
            required_result_identity="item_status bd-ib-4mcuty status closed",
            result_epoch=3,
            original_deadline="2026-10-21T02:00:00Z",
        ),
        opened_at=0.0,
    )


@dataclass(kw_only=True)
class _Reports:
    lines: list[str] = field(default_factory=list)

    def __call__(self, *, text: str) -> None:
        self.lines.append(text)


def _refused_url() -> str:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return f"http://127.0.0.1:{port}/v1/traces"


@pytest.mark.parametrize(
    "condition", ["unconfigured", "unavailable", "partially rejecting", "queue full"]
)
def test_scenario_159_export_degradation_does_not_control_recovery(
    tmp_path: Path, condition: str
) -> None:
    store = tmp_path / "recovery"
    _attempt(store=store)
    reports = _Reports()
    release = threading.Event()

    def partial(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        del url, body, timeout_seconds
        return PostOutcome(delivered=True, rejected_spans=1)

    def blocked(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        del url, body, timeout_seconds
        _ = release.wait(timeout=5.0)
        return PostOutcome(delivered=True)

    def refuse(*, url: str, body: bytes, timeout_seconds: float) -> PostOutcome:
        del url, body, timeout_seconds
        return PostOutcome(delivered=False)

    configured = TelemetryConfig(
        state=STATE_CONFIGURED,
        url=_refused_url(),
        reason=None,
        queue_limit=1 if condition == "queue full" else 64,
        batch_limit=1,
        timeout_seconds=0.2,
        attempts=1,
        shutdown_seconds=0.5,
    )
    telemetry = {
        "unconfigured": SessionTelemetry(config=config_from_environ(environ={}), reporter=reports),
        "unavailable": SessionTelemetry(config=configured, post=refuse, reporter=reports),
        "partially rejecting": SessionTelemetry(config=configured, post=partial, reporter=reports),
        "queue full": SessionTelemetry(config=configured, post=blocked, reporter=reports),
    }[condition]
    command = RecordingCommand(
        effect=RecoveryEffect(
            operation="reconcile-merged:bd-ib-4mcuty",
            identity="gate:20261021T014500Z-7",
            next_action="impl:bd-ib-4mcuty",
        )
    )

    _ = record_transition(
        scope=TransitionScope(
            recovery_store_root=store,
            attempt_id="attempt-159",
            observed_at=200.0,
            telemetry=telemetry,
        ),
        transition=TRANSITION_NOTIFICATION,
    )
    outcome = consume_recovery_obligation(
        request=ConsumerRequest(
            recovery_store_root=store,
            attempt_id="attempt-159",
            consumer="overseerd@hp",
            observed_at=230.0,
            lease_seconds=30.0,
            telemetry=telemetry,
        ),
        evidence=AuthoritativeEvidence(
            item_id="bd-ib-4mcuty",
            epic_id="bd-ib-jnpvh4",
            recorded_next_operation="diagnose-plan-progress:bd-ib-jnpvh4",
            recorded_operation_completed=True,
            ledger_status=Reading(value="active"),
            merged_pull_request=Reading(value="9117b1c8"),
            remote_run_outcome=Reading(value="succeeded"),
            local_gate_outcome="failed",
            recorded_epoch=3,
            current_epoch=3,
        ),
        safety=SafetyState(
            hold=None,
            commit_hook_running=False,
            red_green_pair_open=False,
            session_idle=True,
            notification_unanswered=True,
            prose_deadline=None,
            stale_diagnostic=None,
        ),
        command=command,
        reader=RecordingLookup(),
    )
    release.set()
    report = telemetry.close()

    assert outcome.state == CONSUMER_EXECUTED
    assert command.calls == ["attempt-159:reconcile-merged:bd-ib-4mcuty"]
    assert len(reports.lines) == 1
    expected = {
        "unconfigured": ("local-only", report.exported == 0),
        "unavailable": ("failed=", report.failed >= 1),
        "partially rejecting": ("rejected=", report.rejected >= 1),
        "queue full": ("dropped=", report.dropped >= 1),
    }[condition]
    assert expected[0] in reports.lines[0]
    assert expected[1]

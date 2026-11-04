"""Obligation registration, recovery transitions and coverage publish distinct events.

Scenario 159 asks that obligation recovery "execute" with local deadlines, results
and recovery remaining effective whatever the export does, and the contract's
recovery-family catalog asks for a SEPARATE identity-linked event per durable
observation: registration, notification, receipt, claim, execution start,
execution evidence, safety deferral and the reconciled next action, plus the
graded coverage. Each carries the obligation id, the epoch as an opaque string,
the original deadline and the attempt id; the measurements are the actual
recovery latency and the age past the original deadline; and a value that could
not be measured is OMITTED and named, never published as a zero.

A recovery event describes what a consumer did. It must never claim the
original result was fulfilled — only the canonical result reader can.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_CLAIMED,
    TRANSITION_DEFERRED,
    TRANSITION_EXECUTED,
    TRANSITION_NOTIFICATION,
    TRANSITION_RECEIPT,
    TRANSITION_RECONCILED,
    TRANSITION_STARTED,
    RecoveryAttempt,
    open_recovery_attempt,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_telemetry import (
    TransitionScope,
    record_transition,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import SessionEvent
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import SessionTelemetry
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)

_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_DEADLINE = "2026-10-21T02:00:00Z"
_DUE = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc).timestamp()
_EPOCH = 14
_NEXT_ACTION = "impl:bd-ib-dle6l3"
_TRANSITIONS = [
    "session.recovery.notification",
    "session.recovery.receipt",
    "session.recovery.claimed",
    "session.recovery.started",
    "session.recovery.executed",
    "session.recovery.reconciled",
]


@pytest.fixture(autouse=True)
def hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (_ENDPOINT_ENV, "TRACEPARENT"):
        monkeypatch.delenv(name, raising=False)


@dataclass(kw_only=True)
class _Sink:
    quiet: bool = False
    before_check: Callable[[], None] | None = None
    events: list[SessionEvent] = field(default_factory=list)

    @property
    def exporting(self) -> bool:
        if self.before_check is not None:
            self.before_check()
        return not self.quiet

    def emit(self, *, event: SessionEvent) -> None:
        self.events.append(event)

    def names(self) -> list[str]:
        return [event.name for event in self.events]


def _store(*, tmp_path: Path, deadline: str = _DEADLINE) -> Path:
    store = tmp_path / "recovery"
    _ = open_recovery_attempt(
        recovery_store_root=store,
        attempt=RecoveryAttempt(
            attempt_id="attempt-1",
            operation_id="op-1",
            required_result_identity="item_status bd-ib-dle6l3 status closed",
            result_epoch=_EPOCH,
            original_deadline=deadline,
        ),
        opened_at=0.0,
    )
    return store


def _notify(*, store: Path, sink: _Sink | SessionTelemetry, at: float = _DUE + 10.0) -> str:
    return record_transition(
        scope=TransitionScope(
            recovery_store_root=store, attempt_id="attempt-1", observed_at=at, telemetry=sink
        ),
        transition=TRANSITION_NOTIFICATION,
    )


def _advance(*, store: Path, sink: _Sink | SessionTelemetry, through_deferral: str | None) -> None:
    """Record the transitions a consumer pass writes, at the instants it writes them."""

    def record(*, transition: str, detail: dict[str, object] | None = None) -> None:
        scope = TransitionScope(
            recovery_store_root=store,
            attempt_id="attempt-1",
            observed_at=_DUE + 40.0,
            telemetry=sink,
        )
        _ = record_transition(scope=scope, transition=transition, detail=detail)

    _ = _notify(store=store, sink=sink)
    record(transition=TRANSITION_RECEIPT, detail={"consumer": "overseerd@hp"})
    record(transition=TRANSITION_CLAIMED, detail={"consumer": "overseerd@hp", "generation": 1})
    if through_deferral is not None:
        record(transition=TRANSITION_DEFERRED, detail={"barrier": through_deferral})
        return
    record(transition=TRANSITION_STARTED, detail={"operation": "reconcile-merged:bd-ib-dle6l3"})
    record(transition=TRANSITION_EXECUTED, detail={"identity": "gate:20261021T014500Z-7"})
    record(transition=TRANSITION_RECONCILED, detail={"next_action": _NEXT_ACTION})


def test_each_transition_is_its_own_identity_linked_event_with_its_measurements(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path=tmp_path)
    sink = _Sink()
    _advance(store=store, sink=sink, through_deferral=None)

    assert sink.names() == _TRANSITIONS
    assert len({event.trace_key for event in sink.events}) == 1
    for event in sink.events:
        attributes = event.attributes
        assert attributes["session.obligation.id"] == "op-1"
        assert attributes["session.obligation.epoch"] == "14"
        assert attributes["session.obligation.deadline"] == _DEADLINE
        assert attributes["session.recovery.attempt_id"] == "attempt-1"
        assert attributes["session.recovery.state"] == event.name.removeprefix("session.recovery.")
        assert attributes["session.recovery.duplicate_count"] == 0
        assert attributes["session.recovery.fenced_count"] == 0
        assert "session.recovery.unavailable" not in attributes
        assert "fulfilled" not in " ".join([*attributes, *map(str, attributes.values())])
    notification, receipt, _, started, executed, reconciled = (e.attributes for e in sink.events)
    assert notification["session.observation.time"] == "2026-10-21T02:00:10Z"
    assert "session.recovery.latency_seconds" not in notification
    assert receipt["session.recovery.latency_seconds"] == 30.0
    assert started["session.recovery.latency_seconds"] == 30.0
    assert executed["session.recovery.latency_seconds"] == 30.0
    assert executed["session.obligation.overdue_seconds"] == 40.0
    assert reconciled["session.recovery.next_action"] == _NEXT_ACTION
    assert "session.recovery.next_action" not in executed


@pytest.mark.parametrize(
    ("barrier", "reason"),
    [
        ("human-hold", "human_hold"),
        ("active-commit-hook", "commit_or_hook"),
        ("open-red-green-pair", "red_green_pair"),
    ],
)
def test_a_safety_deferral_publishes_its_reason_and_no_execution(
    tmp_path: Path, barrier: str, reason: str
) -> None:
    store = _store(tmp_path=tmp_path)
    sink = _Sink()
    _advance(store=store, sink=sink, through_deferral=barrier)

    assert sink.names() == [
        "session.recovery.notification",
        "session.recovery.receipt",
        "session.recovery.claimed",
        "session.recovery.deferred",
    ]
    assert sink.events[-1].attributes["session.recovery.deferral_reason"] == reason


def test_a_duplicate_transition_is_counted_not_republished(tmp_path: Path) -> None:
    store = _store(tmp_path=tmp_path)
    sink = _Sink()
    scope = TransitionScope(
        recovery_store_root=store, attempt_id="attempt-1", observed_at=_DUE + 20.0, telemetry=sink
    )
    _ = _notify(store=store, sink=sink)
    first = record_transition(scope=scope, transition=TRANSITION_RECEIPT)
    second = record_transition(scope=scope, transition=TRANSITION_RECEIPT)
    _ = record_transition(scope=scope, transition=TRANSITION_CLAIMED)

    assert (first, second) == ("recorded", "duplicate")
    assert sink.names() == [
        "session.recovery.notification",
        "session.recovery.receipt",
        "session.recovery.claimed",
    ]
    assert sink.events[-1].attributes["session.recovery.duplicate_count"] == 1


def test_a_measurement_that_cannot_be_taken_is_omitted_and_named(tmp_path: Path) -> None:
    store = _store(tmp_path=tmp_path, deadline="after lunch")
    sink = _Sink()
    scope = TransitionScope(
        recovery_store_root=store, attempt_id="attempt-1", observed_at=500.0, telemetry=sink
    )

    _ = record_transition(scope=scope, transition=TRANSITION_RECEIPT)

    assert sink.names() == ["session.recovery.receipt"]
    attributes = sink.events[0].attributes
    assert attributes["session.recovery.unavailable"] == [
        "session.recovery.latency_seconds",
        "session.obligation.overdue_seconds",
    ]
    assert "session.recovery.latency_seconds" not in attributes
    assert "session.obligation.overdue_seconds" not in attributes
    assert attributes["session.obligation.deadline"] == "after lunch"


def test_a_sink_that_is_not_exporting_or_a_record_that_vanished_publishes_nothing(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path=tmp_path)
    quiet = _Sink(quiet=True)
    status = _notify(store=store, sink=quiet)
    assert (status, quiet.events) == ("recorded", [])

    path = recovery_record_path(recovery_store_root=store, attempt_id="attempt-1")
    vanishing = _Sink(before_check=path.unlink)
    scope = TransitionScope(
        recovery_store_root=store, attempt_id="attempt-1", observed_at=1.0, telemetry=vanishing
    )
    assert record_transition(scope=scope, transition=TRANSITION_RECEIPT) == "recorded"
    assert vanishing.events == []


@dataclass(kw_only=True)
class _CapturingExporter:
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return True

    def attributes(self) -> list[tuple[str, dict[str, dict[str, object]]]]:
        return [
            (
                cast("str", span["name"]),
                {
                    cast("str", entry["key"]): cast("dict[str, object]", entry["value"])
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


def test_recovery_events_reach_the_receiver_with_their_types_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path=tmp_path)
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        telemetry = SessionTelemetry.from_environ(environ=dict(os.environ))
        _advance(store=store, sink=telemetry, through_deferral=None)
        report = telemetry.close()

    assert report.exported == len(_TRANSITIONS)
    delivered = exporter.attributes()
    assert [name for name, _ in delivered] == _TRANSITIONS
    executed = delivered[4][1]
    assert executed["session.recovery.latency_seconds"] == {"doubleValue": 30.0}
    assert executed["session.obligation.overdue_seconds"] == {"doubleValue": 40.0}
    assert executed["session.obligation.epoch"] == {"stringValue": "14"}
    assert executed["session.recovery.duplicate_count"] == {"intValue": "0"}
    assert delivered[5][1]["session.recovery.next_action"] == {"stringValue": _NEXT_ACTION}


_SOUND_DECLARATION: dict[str, object] = {
    "max_observation_interval_seconds": 15.0,
    "proof_artifact": "livespec-overseer-consumer@0.1.0",
    "recovery_route": "overseer-supervised-service",
    "runtime": "codex",
    "runtime_version": "0.60.0",
    "service_generation": "7",
    "service_identity": "livespec-overseer-consumer.service",
    "takeover_budget_seconds": 20.0,
    "terminal_backend": "herdr",
    "terminal_instance": "w1:pF",
    "terminal_version": "0.9.3",
}


def _own_root(*, repository: Path) -> Path:
    return repository


def _launch_argv(*, primary: Path) -> list[str]:
    return [
        "launch",
        "--repo",
        str(primary),
        "--session-id",
        "session-h",
        "--invoker",
        "role:coordinator",
        "--scope",
        "plan:agent-session-stall-prevention",
        "--operation-id",
        "op-host-1",
        "--required-result",
        "item_status bd-ib-zejlae status closed",
        "--result-epoch",
        "4",
        "--original-deadline",
        "2026-10-15T12:00:00Z",
        "--gate",
        "g-1",
    ]


def test_the_host_launch_and_complete_commands_publish_through_the_configured_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    declaration = tmp_path / "tmp" / "session-coverage.json"
    declaration.parent.mkdir(parents=True)
    _ = declaration.write_text(json.dumps(_SOUND_DECLARATION), encoding="utf-8")
    run = tmp_path / "tmp" / "gate-runs" / "g-1"
    run.mkdir(parents=True)
    _ = (run / "started_at").write_text("20261015T090000Z\n", encoding="utf-8")
    seams = session_wait.SessionWaitCliSeams(
        primary_repository=_own_root,
        launcher=default_wait_launcher,
        observe_target=observe_wait_target,
        process_generation=process_generation_token,
        wall_clock=lambda: 100.0,
        use_tmp_directory=True,
    )
    with _receiver(tmp_path=tmp_path, monkeypatch=monkeypatch) as exporter:
        launched = session_wait.main(argv=_launch_argv(primary=tmp_path), seams=seams)
        completed = session_wait.main(argv=["complete", "--repo", str(tmp_path)], seams=seams)
    _ = capsys.readouterr()

    assert (launched, completed) == (0, 0)
    delivered = exporter.attributes()
    assert [name for name, _ in delivered] == [
        "session.recovery.coverage",
        "session.obligation.registered",
        "session.recovery.coverage",
    ]
    assert delivered[1][1]["session.obligation.epoch"] == {"stringValue": "4"}
    assert delivered[1][1]["session.id"] == {"stringValue": "session-h"}
    assert delivered[2][1]["session.coverage.state"] == {"stringValue": "verified"}

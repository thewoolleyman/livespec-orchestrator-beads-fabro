"""Tests for the dispatcher's live-OTLP-receiver supervision (29f.7 E1).

The dispatcher idempotently starts ONE host-local live OTLP receiver at
dispatch entry (telemetry-pipeline-architecture.md §3.2 — single-instance,
shared across concurrent dispatches, fail-open toward the pipeline). These
tests exercise that wiring with the server launch MOCKED — no real socket
ever binds, no real fabro run, no real Honeycomb call:

- `ensure_otel_receiver` is driven against an injected holder + fake
  factory (single-instance), and against a raising factory (fail-open).
- the default receiver factory builds (but does NOT start) a real `OtelReceiver`
  with the env-resolved config + journal-sibling heartbeat path.
- `heartbeat_path` derives the journal-sibling heartbeat file.
- The two command entrypoints (`dispatch` / `loop`) invoke the receiver
  arming at entry — verified with `ensure_otel_receiver` monkeypatched to
  a recorder and the command short-circuited on a missing repo (so no real
  receiver / fabro run is reached).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_otel_wiring
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_command import (
    run_loop_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import (
    arm_otel_egress,
    ensure_otel_enrich_driver,
    ensure_otel_receiver,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import heartbeat_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_commands import (
    run_dispatch_command,
)
from livespec_orchestrator_beads_fabro.commands._otel_enrich import HoneycombHttpExporter
from livespec_orchestrator_beads_fabro.commands._otel_enrich_driver import OtelEnrichDriver
from livespec_orchestrator_beads_fabro.commands._otel_receive import OtelReceiver

_EXIT_PRECONDITION_ERROR = 3
_DISPATCH_ARM_TARGET = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_run_commands.arm_otel_egress"
)
_LOOP_ARM_TARGET = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_command.arm_otel_egress"
)
_WIRING_RECEIVER_TARGET = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring.ensure_otel_receiver"
)
_WIRING_ENRICH_TARGET = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring.ensure_otel_enrich_driver"
)


@dataclass(kw_only=True)
class _FakeServer:
    """A startable fake (the `StartableServer` shape); never binds a socket."""

    started: int = 0

    def start(self) -> None:
        self.started += 1


def _args(*, repo: Path, journal: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), journal=None if journal is None else str(journal))


def test_ensure_otel_receiver_is_single_instance(tmp_path: Path) -> None:
    """Two arming calls start exactly ONE receiver (shared across dispatches)."""
    holder: dict[str, object] = {}
    created: list[_FakeServer] = []

    def _factory() -> _FakeServer:
        server = _FakeServer()
        created.append(server)
        return server

    first = ensure_otel_receiver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_factory
    )
    second = ensure_otel_receiver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_factory
    )
    assert first is second
    assert len(created) == 1
    assert created[0].started == 1


def test_ensure_otel_receiver_is_fail_open(tmp_path: Path) -> None:
    """A receiver start failure never raises out toward a dispatch (fail-open)."""
    holder: dict[str, object] = {}

    def _boom() -> _FakeServer:
        raise RuntimeError("port already bound")

    result = ensure_otel_receiver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_boom
    )
    assert result is None
    assert holder == {}


def test_heartbeat_path_is_journal_sibling(tmp_path: Path) -> None:
    """The heartbeat file is co-located with the journal (a sibling file)."""
    journal = tmp_path / "fabro-dispatch-journal.jsonl"
    path = heartbeat_path(args=_args(repo=tmp_path, journal=journal), repo=tmp_path)
    assert path == tmp_path / "fabro-dispatch-journal-otel-heartbeat.json"


def test_default_otel_receiver_factory_builds_without_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default factory returns a configured, UNSTARTED OtelReceiver."""
    monkeypatch.setenv("LIVESPEC_OTEL_RECEIVER_PORT", "0")
    monkeypatch.setenv("HONEYCOMB_INGEST_KEY_LIVESPEC", "ingest-xyz")

    def _without_starting(*, holder: dict[str, object], factory: Callable[[], object]) -> object:
        _ = holder
        return factory()

    monkeypatch.setattr(_dispatcher_otel_wiring, "ensure_receiver_started", _without_starting)
    journal = tmp_path / "j.jsonl"
    receiver = ensure_otel_receiver(
        args=_args(repo=tmp_path, journal=journal), repo=tmp_path, holder={}
    )
    assert isinstance(receiver, OtelReceiver)
    # Port 0 was honored; the receiver is NOT running (never started here).
    assert receiver.config.port == 0
    assert receiver.is_running() is False
    assert receiver.heartbeat.path == tmp_path / "j-otel-heartbeat.json"


@dataclass(kw_only=True)
class _Recorder:
    """Records each OTel arming call (receiver OR enrich driver) a command makes."""

    calls: list[Path] = field(default_factory=list)

    def __call__(self, *, args: argparse.Namespace, repo: Path) -> None:
        _ = args
        self.calls.append(repo)


def test_dispatch_command_arms_otel_egress_at_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `dispatch` command arms the OTel egress plane at entry (before preconditions)."""
    recorder = _Recorder()
    monkeypatch.setattr(_DISPATCH_ARM_TARGET, recorder)
    missing = tmp_path / "does-not-exist"
    args = argparse.Namespace(repo=str(missing), janitor=None, journal=None, fabro_bin=None)
    # A missing repo short-circuits AFTER the arming line; the arming still ran.
    rc = run_dispatch_command(args=args)
    assert rc == _EXIT_PRECONDITION_ERROR
    assert recorder.calls == [missing]


def test_loop_command_arms_otel_egress_at_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `loop` command arms the OTel egress plane at entry (before preconditions)."""
    recorder = _Recorder()
    monkeypatch.setattr(_LOOP_ARM_TARGET, recorder)
    missing = tmp_path / "does-not-exist"
    args = argparse.Namespace(repo=str(missing), janitor=None, journal=None, fabro_bin=None)
    rc = run_loop_command(args=args)
    assert rc == _EXIT_PRECONDITION_ERROR
    assert recorder.calls == [missing]


def test_arm_otel_egress_arms_both_planes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`arm_otel_egress` arms BOTH the live receiver AND the file-tail driver."""
    receiver_calls = _Recorder()
    driver_calls = _Recorder()
    monkeypatch.setattr(_WIRING_RECEIVER_TARGET, receiver_calls)
    monkeypatch.setattr(_WIRING_ENRICH_TARGET, driver_calls)
    arm_otel_egress(args=_args(repo=tmp_path), repo=tmp_path)
    assert receiver_calls.calls == [tmp_path]
    assert driver_calls.calls == [tmp_path]


# --------------------------------------------------------------------------
# File-tail enrich DRIVER wiring (29f.5 — the missing production pump)
# --------------------------------------------------------------------------


def test_ensure_otel_enrich_driver_is_single_instance(tmp_path: Path) -> None:
    """Two arming calls start exactly ONE driver (shared across dispatches)."""
    holder: dict[str, object] = {}
    created: list[_FakeServer] = []

    def _factory() -> _FakeServer:
        server = _FakeServer()
        created.append(server)
        return server

    first = ensure_otel_enrich_driver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_factory
    )
    second = ensure_otel_enrich_driver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_factory
    )
    assert first is second
    assert len(created) == 1
    assert created[0].started == 1


def test_ensure_otel_enrich_driver_is_fail_open(tmp_path: Path) -> None:
    """A driver start failure never raises out toward a dispatch (fail-open)."""
    holder: dict[str, object] = {}

    def _boom() -> _FakeServer:
        raise RuntimeError("thread refused")

    result = ensure_otel_enrich_driver(
        args=_args(repo=tmp_path), repo=tmp_path, holder=holder, factory=_boom
    )
    assert result is None
    assert holder == {}


def test_default_otel_enrich_driver_factory_builds_without_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default factory returns an UNSTARTED driver over the three host
    span-file kinds, wired to the ingest-keyed Honeycomb exporter."""
    monkeypatch.setenv("HONEYCOMB_INGEST_KEY_LIVESPEC", "ingest-xyz")

    def _without_starting(*, holder: dict[str, object], factory: Callable[[], object]) -> object:
        _ = holder
        return factory()

    monkeypatch.setattr(_dispatcher_otel_wiring, "ensure_receiver_started", _without_starting)
    journal = tmp_path / "j.jsonl"
    driver = ensure_otel_enrich_driver(
        args=_args(repo=tmp_path, journal=journal), repo=tmp_path, holder={}
    )
    assert isinstance(driver, OtelEnrichDriver)
    assert driver.is_running() is False
    assert {stage.spans_path for stage in driver.stages} == {
        tmp_path / "j-reflection-spans.jsonl",
        tmp_path / "j-reflector-oob-spans.jsonl",
        tmp_path / "j-cost-report-spans.jsonl",
    }
    exporter = driver.stages[0].exporter
    assert isinstance(exporter, HoneycombHttpExporter)
    assert exporter.ingest_key == "ingest-xyz"

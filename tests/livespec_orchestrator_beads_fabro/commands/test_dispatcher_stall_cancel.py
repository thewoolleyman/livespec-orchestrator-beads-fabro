"""Tests for cancelling a stalled Fabro run without deleting its record."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_stall_cancel
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    WatchdogRunReading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroCommandResult


@dataclass(kw_only=True)
class _ServerApi:
    cancel_calls: list[tuple[str, float]] = field(default_factory=list)

    def cancel(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        self.cancel_calls.append((run_id, timeout_seconds))
        return FabroHttpResult(status=200, body="", error=None, payload=None, succeeded=True)


@dataclass(kw_only=True)
class _Port:
    api: _ServerApi
    rm_calls: list[tuple[str, float]] = field(default_factory=list)

    def server_api(self) -> _ServerApi:
        return self.api

    def rm(self, *, run_id: str, timeout_seconds: float) -> FabroCommandResult:
        self.rm_calls.append((run_id, timeout_seconds))
        return FabroCommandResult(command=CommandResult(exit_code=0, stdout="", stderr=""))


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-u6dglg",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )


def test_a_stall_cancel_uses_the_server_cancel_route_and_never_removes_the_run(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The watchdog preserves inspectable evidence by cancelling in place."""
    api = _ServerApi()
    port = _Port(api=api)
    journal = _Journal()
    monkeypatch.setattr(
        _dispatcher_stall_cancel,
        "watchdog_run_reading",
        lambda **_kwargs: WatchdogRunReading(events_json="[]", record_text=""),
    )

    _dispatcher_stall_cancel.cancel_stalled_run(
        dispatch_id="dispatch-1",
        plan=_plan(tmp_path=tmp_path),
        port=cast("FabroPort", port),
        journal=journal,
        run_id="01RUN",
        quiet_seconds=7200.0,
    )

    assert api.cancel_calls == [("01RUN", _dispatcher_stall_cancel.FABRO_RM_TIMEOUT_SECONDS)]
    assert port.rm_calls == []
    assert journal.records[0]["run_id"] == "01RUN"

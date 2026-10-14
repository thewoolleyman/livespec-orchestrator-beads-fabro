"""A closed command cannot shelter a run whose two progress sources freeze."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_io_fabro_launcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import StallWindow
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink


@dataclass(kw_only=True)
class _Runner:
    events: str
    cancelled: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        if argv[1] == "events":
            return CommandResult(exit_code=0, stdout=self.events, stderr="")
        if argv[1] == "ps":
            return CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    [
                        {
                            "run_id": "01RUN",
                            "goal": "Work-item: bd-ib-qsk4o5",
                            "status": {"kind": "running"},
                        }
                    ]
                ),
                stderr="",
            )
        assert argv[1] in ("run", "rm")
        if argv[1] == "rm":
            self.cancelled.append("01RUN")
        return CommandResult(exit_code=0, stdout="Run: 01RUN\n", stderr="")


@dataclass(kw_only=True)
class _Thread:
    """Deterministic scheduling: no real worker can race the scripted poller."""

    target: Callable[[], None]
    runner: _Runner
    daemon: bool = False
    polls: int = 0

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        self.polls += 1
        return not self.runner.cancelled and self.polls < 12

    def join(self, *, timeout: float | None = None) -> None:
        _ = timeout
        self.target()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@pytest.mark.parametrize("ending", ["command.completed", "stage.completed", "stage.failed"])
def test_closed_command_and_frozen_sources_are_cancelled_as_stalled(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
) -> None:
    start = 1_800_000_000.0
    runner = _Runner(
        events=json.dumps(
            [
                {
                    "ts": start,
                    "event": "command.started",
                    "node_id": "janitor",
                    "stage_id": "janitor@1",
                    "properties": {"timeout_ms": 3_600_000},
                },
                {"ts": start + 100, "event": ending, "node_id": "janitor", "stage_id": "janitor@1"},
                {"ts": start + 150, "event": "agent.acp.started", "node_id": "implement"},
            ]
        )
    )

    def _thread(*, target: Callable[[], None], name: str) -> _Thread:
        _ = name
        return _Thread(target=target, runner=runner)

    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "threading", SimpleNamespace(Thread=_thread))
    monkeypatch.setattr(time, "time", lambda: start + 200)
    heartbeat_path = tmp_path / "heartbeat.json"
    HeartbeatSink(path=heartbeat_path).beat(key="dispatch", at=start - 1)
    ticks = iter([0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0])
    journal = _Journal()
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-qsk4o5",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
        stall_window=StallWindow(seconds=1500, layer=REPOSITORY_LAYER),
    )
    result = WatchedFabroLauncher(
        clock=lambda: next(ticks),
        sleep=lambda _seconds: None,
        heartbeat_path=heartbeat_path,
        dispatch_id="dispatch",
    ).launch(plan=plan, runner=runner, journal=journal)
    assert result.stalled_run_id == "01RUN"
    assert runner.cancelled == ["01RUN"]
    cancels = [
        record for record in journal.records if record.get("stage") == "watchdog-stall-cancel"
    ]
    assert len(cancels) == 1
    assert cancels[0]["quiet_seconds"] == 1500.0

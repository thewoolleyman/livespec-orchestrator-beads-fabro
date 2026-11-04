"""The watchdog retains event facts while each later read is incremental."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_io_liveness_probe
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return self.results.pop(0)


def _event_stream(*, event: str) -> str:
    return json.dumps(
        [
            {
                "event": event,
                "node_id": "janitor",
                "timestamp": "2026-11-02T19:00:00Z",
            }
        ]
    )


def test_incremental_event_reads_retain_one_watchs_established_facts(tmp_path: Path) -> None:
    """A delta retains the first reading until it supplies a completion."""
    assert "state" in inspect.signature(liveness_sample).parameters
    state = _dispatcher_io_liveness_probe.LivenessState()
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout=_event_stream(event="stage.started"), stderr=""),
            CommandResult(exit_code=0, stdout="[]", stderr=""),
            CommandResult(exit_code=0, stdout=_event_stream(event="stage.completed"), stderr=""),
        ]
    )
    port = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.example.test"),
        runner=runner,
        cwd=tmp_path,
    )
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-u6llci",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    first = liveness_sample(
        plan=plan,
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=1.0,
        state=state,
    )
    retained = liveness_sample(
        plan=plan,
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=2.0,
        state=state,
    )
    completed = liveness_sample(
        plan=plan,
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=3.0,
        state=state,
    )

    assert first.last_event_epoch is not None
    assert first.open_command_node is not None
    assert retained.last_event_epoch == first.last_event_epoch
    assert retained.open_command_node == first.open_command_node
    assert completed.last_event_epoch == first.last_event_epoch
    assert completed.open_command_node is None
    assert runner.calls == [
        ["fabro", "events", "01RUN", "--json", "--server", "https://factory.example.test"],
        [
            "fabro",
            "events",
            "01RUN",
            "--json",
            "--since",
            "2026-11-02T19:00:00Z",
            "--server",
            "https://factory.example.test",
        ],
        [
            "fabro",
            "events",
            "01RUN",
            "--json",
            "--since",
            "2026-11-02T19:00:00Z",
            "--server",
            "https://factory.example.test",
        ],
    ]

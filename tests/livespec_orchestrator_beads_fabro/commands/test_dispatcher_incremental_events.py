"""The watchdog retains event facts while its next read is incremental."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_open_command_node import (
    updated_open_command_node,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import OpenCommandNode
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._node_timeouts import DEFAULT_NODE_TIMEOUTS


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


def _event_stream(*, name: str) -> str:
    return json.dumps(
        [
            {
                "event": name,
                "node_id": "janitor",
                "timestamp": "2026-11-02T19:00:00Z",
            }
        ]
    )


def test_incremental_event_reads_keep_an_open_command_and_the_latest_progress(
    tmp_path: Path,
) -> None:
    """An empty delta retains facts from the full read; a later ending clears only the node."""
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout=_event_stream(name="stage.started"), stderr=""),
            CommandResult(exit_code=0, stdout="[]", stderr=""),
            CommandResult(exit_code=0, stdout=_event_stream(name="stage.completed"), stderr=""),
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
    )
    retained = liveness_sample(
        plan=plan,
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=2.0,
    )
    completed = liveness_sample(
        plan=plan,
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=3.0,
    )

    assert first.last_event_epoch is not None
    assert first.open_command_node is not None
    assert first.open_command_node.node == "janitor"
    assert retained.last_event_epoch == first.last_event_epoch
    assert retained.open_command_node == first.open_command_node
    assert completed.last_event_epoch == first.last_event_epoch
    assert completed.open_command_node is None
    assert runner.calls[0] == [
        "fabro",
        "events",
        "01RUN",
        "--json",
        "--server",
        "https://factory.example.test",
    ]
    assert runner.calls[1] == [
        "fabro",
        "events",
        "01RUN",
        "--json",
        "--since",
        "2026-11-02T19:00:00Z",
        "--server",
        "https://factory.example.test",
    ]


def test_an_unreadable_event_delta_keeps_the_established_command_node() -> None:
    established = OpenCommandNode(node="janitor", timeout_seconds=1800.0)

    assert (
        updated_open_command_node(
            established=established,
            events_json="not-json",
            timeouts=DEFAULT_NODE_TIMEOUTS,
        )
        == established
    )

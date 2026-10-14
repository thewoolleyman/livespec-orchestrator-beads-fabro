"""Command timeouts protect quiet nodes without inventing event progress."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import liveness_sample
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    StallVerdict,
    decide_stall,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import fabro_port_for_plan
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink


@dataclass(kw_only=True)
class _EventsRunner:
    events: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        assert argv[1:3] == ["events", "01RUN"]
        return CommandResult(exit_code=0, stdout=self.events, stderr="")


@pytest.mark.parametrize("node", ["janitor", "publish_draft", "custom_command"])
@pytest.mark.parametrize("heartbeat", [None, 900.0, 1050.0])
def test_quiet_command_is_protected_until_its_configured_timeout(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    node: str,
    heartbeat: float | None,
) -> None:
    # Fabro 0.254 serializes CommandStarted with this exact properties shape.
    # The reported 2000-second timeout deliberately differs from the default.
    started = 1_800_000_000.0
    events = json.dumps(
        [
            {
                "ts": started,
                "event": "command.started",
                "node_id": node,
                "stage_id": f"{node}@1",
                "properties": {"timeout_ms": 2_000_000},
            }
        ]
    )
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-qsk4o5",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    port = fabro_port_for_plan(plan=plan, runner=_EventsRunner(events=events))
    heartbeat_path = None
    if heartbeat is not None:
        heartbeat_path = tmp_path / "heartbeat.json"
        HeartbeatSink(path=heartbeat_path).beat(key="dispatch", at=started + heartbeat - 1000)
    samples = []
    for elapsed in (0.0, 1500.0, 1999.0, 2000.0):
        monkeypatch.setattr(time, "time", lambda elapsed=elapsed: started + elapsed)
        sample = liveness_sample(
            plan=plan,
            port=port,
            run_id="01RUN",
            heartbeat_path=heartbeat_path,
            dispatch_id="dispatch",
            observed_at=100.0 + elapsed,
        )
        samples.append(sample)
        verdict = decide_stall(samples=tuple(samples), stall_seconds=1500.0)
        expected = StallVerdict.CONTINUE if elapsed < 2000 else StallVerdict.STALLED
        assert verdict is expected
        assert sample.last_event_epoch == started + max(0.0, (heartbeat or 0.0) - 1000)

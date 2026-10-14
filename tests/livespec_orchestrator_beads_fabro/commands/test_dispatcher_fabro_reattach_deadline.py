"""Inspection latency and scheduler delays consume the visibility window."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import (
    ReattachTiming,
    inspect_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import (
    Journal,
    Runner,
)


@dataclass(kw_only=True)
class Clock:
    elapsed: float = 0.0

    def read(self) -> float:
        return self.elapsed

    def advance(self, *, seconds: float) -> None:
        self.elapsed += seconds


@dataclass(kw_only=True)
class TimedRunner:
    clock: Clock
    request_seconds: float
    timeouts: list[float] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, env, stdin)
        self.timeouts.append(timeout_seconds)
        self.clock.advance(seconds=min(self.request_seconds, timeout_seconds))
        return CommandResult(exit_code=1, stdout="", stderr="inspect timed out")


def plan_for_test(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-w3k6dm",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
    )


@pytest.mark.parametrize(("request_seconds", "overshoot"), [(300.0, 0.0), (0.0, 600.0)])
def test_inspect_and_sleep_share_one_wall_clock_deadline(
    *, tmp_path: Path, request_seconds: float, overshoot: float
) -> None:
    clock = Clock()
    runner = TimedRunner(clock=clock, request_seconds=request_seconds)
    result = inspect_run(
        plan=plan_for_test(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        run_id="01DROPPED",
        follow_live=True,
        timing=ReattachTiming(
            sleep=lambda seconds: clock.advance(seconds=seconds + overshoot), clock=clock.read
        ),
    )
    assert result is not None
    assert result.command.exit_code == 1
    assert runner.timeouts == ([300.0, 295.0] if request_seconds else [300.0])
    assert clock.elapsed == (600.0 if request_seconds else 605.0)


@pytest.mark.parametrize("payload", ["{}", "broken json", '[{"status":{"kind":"novel"}}]'])
def test_unrecognized_inspect_payload_is_retried_not_terminal(
    *, tmp_path: Path, payload: str
) -> None:
    runner = Runner(replies=[CommandResult(exit_code=0, stdout=payload, stderr="")] * 12)
    sleeps: list[float] = []
    result = inspect_run(
        plan=plan_for_test(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        run_id="01DROPPED",
        follow_live=True,
        timing=ReattachTiming(sleep=sleeps.append, clock=lambda: 0.0),
    )
    assert result is not None
    assert len(runner.calls) == 12
    assert len(sleeps) == 11

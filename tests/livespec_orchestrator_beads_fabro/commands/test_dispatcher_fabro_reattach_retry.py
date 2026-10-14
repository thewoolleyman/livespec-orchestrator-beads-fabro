"""An unanswered inspect is not evidence that its run failed."""

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import (
    Journal,
    Runner,
)


@pytest.mark.parametrize("recovers", [True, False])
def test_inspect_timeouts_retry_with_bounded_backoff(*, tmp_path: Path, recovers: bool) -> None:
    timeout = CommandResult(exit_code=1, stdout="", stderr="server request timed out after 30s")
    live = CommandResult(exit_code=0, stdout='[{"status":{"kind":"running"}}]', stderr="")
    blocked = CommandResult(exit_code=0, stdout='[{"status":{"kind":"blocked"}}]', stderr="")
    observations = [timeout, timeout, live, timeout, blocked] if recovers else [timeout] * 12
    runner = Runner(
        replies=[
            CommandResult(
                exit_code=1,
                stdout="Run: 01DROPPED\n",
                stderr="error decoding response body: timed out",
            ),
            *observations,
        ]
    )
    plan = replace(
        build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-w3k6dm",
            workflow_toml=tmp_path / "workflow.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor",
        ),
        fabro_factory_server="https://factory.example:32276",
    )
    sleeps: list[float] = []
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=Journal(),
        sleep=sleeps.append,
        poll=PollPolicy(attempts=1, interval_seconds=0),
    )
    assert len(runner.calls) == 1 + len(observations)
    assert outcome.fabro_run_id == "01DROPPED"
    assert all(argv[-2:] == ["--server", plan.fabro_factory_server] for argv in runner.calls)
    assert all(argv[1:3] == ["inspect", "01DROPPED"] for argv in runner.calls[1:])
    if recovers:
        assert outcome.status == "blocked"
        assert sleeps == [5.0, 10.0, 30.0, 5.0]
    else:
        assert sleeps == [5.0, 10.0, 20.0, 40.0, *([60.0] * 7)]
        assert sum(sleeps) < 600

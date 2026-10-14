"""A dead client stream does not terminate the bound server run."""

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan


@dataclass(kw_only=True)
class Runner:
    replies: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return self.replies.pop(0)


@dataclass(kw_only=True)
class Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_stream_drop_keeps_polling_bound_run_until_terminal(*, tmp_path: Path) -> None:
    runner = Runner(
        replies=[
            CommandResult(
                exit_code=1,
                stdout="Run: 01DROPPED\n",
                stderr="error decoding response body: timed out",
            ),
            CommandResult(exit_code=0, stdout='[{"status":{"kind":"running"}}]', stderr=""),
            CommandResult(exit_code=0, stdout='[{"status":{"kind":"running"}}]', stderr=""),
            CommandResult(exit_code=0, stdout='[{"status":{"kind":"blocked"}}]', stderr=""),
        ]
    )
    journal = Journal()
    sleeps: list[float] = []
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-w3k6dm",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=sleeps.append,
        poll=PollPolicy(attempts=1, interval_seconds=0),
    )
    assert outcome.status == "blocked"
    assert outcome.fabro_run_id == "01DROPPED"
    assert len(sleeps) == 2
    assert all(delay > 0 for delay in sleeps)
    assert [argv[1:3] for argv in runner.calls[1:]] == [["inspect", "01DROPPED"]] * 3
    assert not runner.replies

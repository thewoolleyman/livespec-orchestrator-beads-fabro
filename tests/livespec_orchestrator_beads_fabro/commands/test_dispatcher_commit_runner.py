"""The fake-driven verdict boundary of the detached sandbox commit runner."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPOSITORY_ROOT / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_commit_runner.py"
)


@dataclass
class _FakeClock:
    now: float = 0.0

    def sleep(self, *, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class _FakeProcess:
    completes_at: float
    exit_code: int
    output: str

    def poll(self, *, now: float) -> int | None:
        return self.exit_code if now >= self.completes_at else None


@dataclass
class _FakeLauncher:
    process: _FakeProcess
    commands: list[tuple[str, ...]]

    def launch(self, *, command: tuple[str, ...]) -> _FakeProcess:
        self.commands.append(command)
        return self.process


def test_wait_records_a_hook_refusal_after_an_earlier_wait_returns_running() -> None:
    """The commit process, rather than its first bounded wait, supplies the verdict."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )
    clock = _FakeClock()
    command = ("mise", "exec", "--", "git", "commit", "--amend", "--no-edit")
    launcher = _FakeLauncher(
        process=_FakeProcess(
            completes_at=2.0,
            exit_code=1,
            output="Failed targets (2):\n  - check-types\n  - check-tests\n",
        ),
        commands=[],
    )
    runner = module.DetachedCommitRunner(launcher=launcher, clock=clock)

    run_id = runner.start(command=command)
    early = runner.wait(run_id=run_id, timeout_seconds=1)
    terminal = runner.wait(run_id=run_id, timeout_seconds=2)

    assert launcher.commands == [command]
    assert early.state == "running"
    assert terminal.state == "failed"
    assert terminal.exit_code == 1
    assert terminal.failed_targets == ("check-types", "check-tests")


def test_wait_returns_the_recorded_terminal_verdict_without_polling_again() -> None:
    """A terminal verdict stays authoritative for every later bounded wait."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )
    clock = _FakeClock()
    launcher = _FakeLauncher(
        process=_FakeProcess(
            completes_at=0.0,
            exit_code=0,
            output="",
        ),
        commands=[],
    )
    runner = module.DetachedCommitRunner(launcher=launcher, clock=clock)

    run_id = runner.start(command=("git", "commit", "-m", "test"))
    terminal = runner.wait(run_id=run_id, timeout_seconds=0.0)

    assert runner.wait(run_id=run_id, timeout_seconds=0.0) is terminal


def test_materialized_runner_executes_the_tracked_cli() -> None:
    """The sandbox executable delegates to the state machine's real-process adapter."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )

    source = module.commit_runner_program_source()

    assert "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_cli" in source

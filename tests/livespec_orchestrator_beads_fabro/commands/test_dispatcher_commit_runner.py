"""The detached commit runner's fake-driven terminal-state observations."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _FakeClock:
    now: float = 0.0

    def sleep(self, *, seconds: float) -> None:
        self.now += seconds


@dataclass
class _FakeProcess:
    clock: _FakeClock
    terminal_at: float
    exit_code: int
    output: str
    poll_count: int = field(default=0, init=False)

    def poll(self, *, now: float) -> int | None:
        del now
        self.poll_count += 1
        return self.exit_code if self.clock.now >= self.terminal_at else None


@dataclass
class _FakeLauncher:
    process: _FakeProcess
    commands: list[tuple[str, ...]]

    def launch(self, *, command: tuple[str, ...]) -> _FakeProcess:
        self.commands.append(command)
        return self.process


def test_runner_records_the_hook_verdict_after_a_bounded_wait() -> None:
    """A later wait records the process verdict rather than its earlier timeout."""
    module_path = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_commit_runner.py"
    )
    assert module_path.is_file()
    runner_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )
    clock = _FakeClock()
    launcher = _FakeLauncher(
        process=_FakeProcess(
            clock=clock,
            terminal_at=2.0,
            exit_code=1,
            output="hook output\nFailed targets\n  - check-coverage\n",
        ),
        commands=[],
    )
    runner = runner_module.DetachedCommitRunner(launcher=launcher, clock=clock)

    run_id = runner.start(command=("git", "commit", "-m", "test"))

    assert runner.wait(run_id=run_id, timeout_seconds=1.0).state == "running"
    verdict = runner.wait(run_id=run_id, timeout_seconds=1.0)

    assert launcher.commands == [("git", "commit", "-m", "test")]
    assert verdict.state == "failed"
    assert verdict.exit_code == 1
    assert verdict.failed_targets == ("check-coverage",)
    assert runner.wait(run_id=run_id, timeout_seconds=0.0) == verdict


def test_runner_leaves_an_unfinished_hook_running() -> None:
    """A bounded wait does not turn a live hook into a failed commit."""
    runner_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )
    clock = _FakeClock()
    launcher = _FakeLauncher(
        process=_FakeProcess(
            clock=clock,
            terminal_at=3.0,
            exit_code=0,
            output="",
        ),
        commands=[],
    )
    runner = runner_module.DetachedCommitRunner(launcher=launcher, clock=clock)

    run_id = runner.start(command=("git", "commit", "-m", "test"))
    report = runner.wait(run_id=run_id, timeout_seconds=2.0)

    assert report.state == "running"
    assert report.exit_code is None
    assert report.failed_targets == ()


def test_runner_reuses_a_terminal_verdict_without_polling_again() -> None:
    """Later waits return the stored verdict instead of re-observing the process."""
    runner_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )
    clock = _FakeClock()
    process = _FakeProcess(
        clock=clock,
        terminal_at=0.0,
        exit_code=0,
        output="",
    )
    runner = runner_module.DetachedCommitRunner(
        launcher=_FakeLauncher(process=process, commands=[]),
        clock=clock,
    )

    run_id = runner.start(command=("git", "commit", "-m", "test"))
    verdict = runner.wait(run_id=run_id, timeout_seconds=0.0)
    observed_polls = process.poll_count

    assert runner.wait(run_id=run_id, timeout_seconds=0.0) is verdict
    assert process.poll_count == observed_polls

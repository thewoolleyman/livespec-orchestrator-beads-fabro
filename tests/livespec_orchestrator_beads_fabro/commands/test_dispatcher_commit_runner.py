"""The fake-driven verdict boundary of the detached commit runner's state machine.

Work-item `bd-ib-atyefi`; `SPECIFICATION/contracts.md` "A commit leg completes
past one tool call". The runner is driven only through an injected fake process
launcher and fake clock -- no real subprocess and no real sleep, per
`check-tests-no-subprocess-spawn` and the item's rider -- so these cases
exercise the state machine itself: a bounded wait that expires reports
`running`, the commit's own process supplies the terminal verdict whenever it
later finishes, and a process gone without one reports `no-verdict`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner import (
    CommitRunResult,
    DetachedCommitRunner,
    failed_targets,
    result_from_observation,
)


@dataclass
class _FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def sleep(self, *, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class _FakeProcess:
    clock: _FakeClock
    completes_at: float | None
    exit_code: int = 0
    output: str = ""
    vanishes_at: float | None = None
    polls: int = 0

    def poll(self, *, now: float) -> int | None:
        self.polls += 1
        if self.completes_at is not None and now >= self.completes_at:
            return self.exit_code
        return None

    def ended_without_verdict(self) -> bool:
        return self.vanishes_at is not None and self.clock.now >= self.vanishes_at


@dataclass
class _FakeLauncher:
    process: _FakeProcess
    commands: list[tuple[str, ...]] = field(default_factory=list)

    def launch(self, *, command: tuple[str, ...]) -> _FakeProcess:
        self.commands.append(command)
        return self.process


_AMEND = ("mise", "exec", "--", "git", "commit", "--amend", "--no-edit")
_REFUSAL = "hook output\nFailed targets (2):\n  - check-types\n  - check-tests\n"


def _runner(process: _FakeProcess) -> tuple[DetachedCommitRunner, _FakeLauncher]:
    launcher = _FakeLauncher(process=process)
    return DetachedCommitRunner(launcher=launcher, clock=process.clock), launcher


def test_a_hook_that_outlasts_the_first_wait_has_its_refusal_recorded_by_a_later_one() -> None:
    """The commit process, not the bounded wait that expired, supplies the verdict."""
    clock = _FakeClock()
    runner, launcher = _runner(
        _FakeProcess(clock=clock, completes_at=2.0, exit_code=1, output=_REFUSAL)
    )

    run_id = runner.start(command=_AMEND)
    early = runner.wait(run_id=run_id, timeout_seconds=1.0)
    terminal = runner.wait(run_id=run_id, timeout_seconds=5.0)

    assert launcher.commands == [_AMEND]
    assert early == CommitRunResult(state="running", exit_code=None, failed_targets=())
    assert terminal == CommitRunResult(
        state="failed", exit_code=1, failed_targets=("check-types", "check-tests")
    )
    assert clock.now == 2.0


def test_a_hook_still_running_when_the_wait_expires_is_reported_running_not_failed() -> None:
    """An expired bound is an observation of a live commit, never a failed commit."""
    clock = _FakeClock()
    runner, _ = _runner(_FakeProcess(clock=clock, completes_at=None))

    run_id = runner.start(command=_AMEND)
    report = runner.wait(run_id=run_id, timeout_seconds=2.5)

    assert report.state == "running"
    assert report.terminal is False
    assert report.exit_code is None
    assert clock.sleeps == [1.0, 1.0, 0.5]


def test_a_recorded_terminal_verdict_is_returned_again_without_polling() -> None:
    """A terminal verdict stays authoritative for every later bounded wait."""
    clock = _FakeClock()
    process = _FakeProcess(clock=clock, completes_at=0.0, exit_code=0)
    runner, _ = _runner(process)

    run_id = runner.start(command=("git", "commit", "-m", "test"))
    terminal = runner.wait(run_id=run_id, timeout_seconds=0.0)

    assert runner.wait(run_id=run_id, timeout_seconds=10.0) is terminal
    assert terminal == CommitRunResult(state="passed", exit_code=0, failed_targets=())
    assert process.polls == 1


def test_a_process_gone_without_a_verdict_reports_no_verdict() -> None:
    """A commit ended by a signal, or vanished, is not a commit and not a refusal."""
    clock = _FakeClock()
    runner, _ = _runner(_FakeProcess(clock=clock, completes_at=None, vanishes_at=1.0))

    run_id = runner.start(command=_AMEND)
    report = runner.wait(run_id=run_id, timeout_seconds=5.0)

    assert report == CommitRunResult(state="no-verdict", exit_code=None, failed_targets=())
    assert report.terminal is True
    assert clock.now == 1.0


def test_each_start_is_its_own_run() -> None:
    """Two starts are two runs with distinct identities."""
    clock = _FakeClock()
    runner, launcher = _runner(_FakeProcess(clock=clock, completes_at=None))

    first = runner.start(command=_AMEND)
    second = runner.start(command=("git", "commit", "-m", "next"))

    assert first != second
    assert len(launcher.commands) == 2


def test_the_terminal_normalizer_names_only_the_aggregate_s_own_failed_targets() -> None:
    """The target list ends at the first line that is not a target."""
    output = (
        "  - not-a-target-before-the-header\nFailed targets (1):\n  - check-types\n"
        "error: Recipe `check-pre-commit` failed\n  - not-a-target-after-it\n"
    )

    assert failed_targets(output=output) == ("check-types",)
    assert failed_targets(output="no aggregate list here\n") == ()
    assert result_from_observation(exit_code=0, output=_REFUSAL).failed_targets == ()
    assert result_from_observation(exit_code=3, output="").state == "failed"

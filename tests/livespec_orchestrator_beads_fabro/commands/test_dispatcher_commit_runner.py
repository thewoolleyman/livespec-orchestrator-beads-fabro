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


def test_materialized_runner_installs_a_detached_commit_entrypoint() -> None:
    """The sandbox receives the same runner the committing prompts name."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner"
    )

    block = module.commit_runner_prepare_steps_block()
    source = module.commit_runner_program_source()

    assert module.COMMIT_RUNNER_PROGRAM_FILENAME == "livespec-commit-runner"
    assert module.commit_runner_program_path_expansion() in block
    assert "chmod 700" in block
    assert "def worker(" in source
    assert "start_new_session=True" in source
    assert "subprocess.run" in source


def test_committing_prompts_direct_commits_through_the_materialized_runner() -> None:
    """An ACP turn can use bounded waits instead of ending with a live hook."""
    for prompt_name in ("implement.md", "fix.md", "review-fix.md"):
        prompt = (
            _REPOSITORY_ROOT
            / ".claude-plugin/.fabro/workflows/implement-work-item/prompts"
            / prompt_name
        ).read_text(encoding="utf-8")

        assert "livespec-commit-runner start -- git commit" in prompt
        assert "livespec-commit-runner wait" in prompt

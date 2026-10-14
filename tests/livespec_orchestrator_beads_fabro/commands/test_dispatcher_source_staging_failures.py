"""Failure and delegation paths of the source-worktree command runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_source_staging as staging
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_refusals import (
    not_a_worktree_outcome,
    pass_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_waivers import StepWaiver

_HEAD = "a" * 40


@dataclass(kw_only=True)
class _Runner:
    fail: tuple[str, ...] = ()
    remote: str = "same"
    explode: bool = False
    calls: list[tuple[list[str], Path, float, dict[str, str] | None, int | None]] = field(
        default_factory=list
    )
    branch: str = ""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        self.calls.append((argv, cwd, timeout_seconds, env, stdin))
        if argv[:3] == ["git", "worktree", "add"]:
            self.branch = argv[4]
        if self.explode and argv[:2] == ["fabro", "run"]:
            raise RuntimeError("launch bug")
        if self.fail and tuple(argv[: len(self.fail)]) == self.fail:
            return CommandResult(exit_code=1, stdout="", stderr="injected failure")
        stdout = ""
        if argv[:2] == ["git", "ls-remote"] and self.remote != "absent":
            head = _HEAD if self.remote == "same" else "b" * 40
            stdout = f"{head}\trefs/heads/{self.branch}\n"
        if argv[:2] == ["git", "rev-parse"]:
            # The fetched default-branch head. This checkout is AT it, so these
            # cases stage at their own HEAD and the base decision is not what
            # they are varying.
            stdout = f"{_HEAD}\n"
        return CommandResult(exit_code=0, stdout=stdout, stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@pytest.fixture
def source_runner(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> staging.SourceStagingRunner:
    monkeypatch.setattr(
        staging,
        "source_checkout_preflight",
        lambda **_: pass_outcome(
            head=_HEAD, origin_refs=("origin/other", "origin/master"), origin_ref="origin/master"
        ),
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return staging.SourceStagingRunner(
        inner=_Runner(),
        journal=_Journal(),
        plan=build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-urhjxd",
            workflow_toml=tmp_path / "workflow.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor",
            default_branch="master",
        ),
    )


def _launch(*, runner: staging.SourceStagingRunner) -> CommandResult:
    return runner.run(
        argv=["fabro", "run", "workflow.toml"],
        cwd=runner.plan.repo,
        timeout_seconds=71,
        env={"FABRO_SERVER": "https://factory.example"},
        stdin=0,
    )


def test_another_repositories_launch_is_not_staged(
    *, source_runner: staging.SourceStagingRunner
) -> None:
    inner = source_runner.inner
    assert isinstance(inner, _Runner)
    other = source_runner.plan.repo / "other"
    source_runner.run(argv=["fabro", "run"], cwd=other, timeout_seconds=19)
    assert inner.calls == [(["fabro", "run"], other, 19, None, None)]


def test_the_actual_launch_keeps_argv_timeout_environment_and_stdin(
    *, source_runner: staging.SourceStagingRunner
) -> None:
    inner = source_runner.inner
    assert isinstance(inner, _Runner)
    assert _launch(runner=source_runner).exit_code == 0
    call = next(call for call in inner.calls if call[0][:2] == ["fabro", "run"])
    assert call[0] == ["fabro", "run", "workflow.toml"]
    assert call[1].is_relative_to(
        source_runner.plan.repo / ".worktrees" / source_runner.plan.repo.name
    )
    assert call[2:] == (71, {"FABRO_SERVER": "https://factory.example"}, 0)
    deletion = next(call for call in inner.calls if call[0][:2] == ["git", "push"])
    assert deletion[1] == call[1]
    assert deletion[2] == source_runner.plan.fabro_timeout_seconds
    assert deletion[0] == [
        "git",
        "push",
        f"--force-with-lease=refs/heads/{inner.branch}:{_HEAD}",
        "origin",
        f":refs/heads/{inner.branch}",
    ]


@pytest.mark.parametrize("waived", [False, True])
def test_rechecking_refuses_before_staging_unless_the_step_is_explicitly_waived(
    *, source_runner: staging.SourceStagingRunner, monkeypatch: pytest.MonkeyPatch, waived: bool
) -> None:
    monkeypatch.setattr(
        staging, "source_checkout_preflight", lambda **_: not_a_worktree_outcome(repo="missing")
    )
    waivers = (
        (StepWaiver(step="source-checkout", owner="operator", reason="explicit"),) if waived else ()
    )
    monkeypatch.setattr(staging, "resolve_step_waivers", lambda **_: waivers)
    result = _launch(runner=source_runner)
    inner, journal = source_runner.inner, source_runner.journal
    assert isinstance(inner, _Runner)
    assert isinstance(journal, _Journal)
    if waived:
        assert result.exit_code == 0
        assert inner.calls[0][1] == source_runner.plan.repo
        assert len(journal.records) == 2
    else:
        assert result.exit_code == 3
        assert "not a Git worktree" in result.stderr
        assert not inner.calls
    assert not any(row["stage"] == "source-checkout-stage" for row in journal.records)


@pytest.mark.parametrize("failure", [("git", "worktree", "add"), ("fabro", "run")])
def test_creation_or_launch_failure_is_returned_and_cleanup_is_attempted(
    *, source_runner: staging.SourceStagingRunner, failure: tuple[str, ...]
) -> None:
    inner = source_runner.inner
    assert isinstance(inner, _Runner)
    inner.fail = failure
    assert _launch(runner=source_runner).exit_code == 1
    assert any(call[0][:3] == ["git", "worktree", "remove"] for call in inner.calls)
    assert any(call[0][:3] == ["git", "update-ref", "-d"] for call in inner.calls)
    if failure[-1] == "add":
        assert not any(call[0][:2] == ["fabro", "run"] for call in inner.calls)


def test_launch_bug_propagates_after_cleanup(*, source_runner: staging.SourceStagingRunner) -> None:
    inner = source_runner.inner
    assert isinstance(inner, _Runner)
    inner.explode = True
    with pytest.raises(RuntimeError, match="launch bug"):
        _launch(runner=source_runner)
    assert any(call[0][:3] == ["git", "worktree", "remove"] for call in inner.calls)


@pytest.mark.parametrize("remote", ["absent", "changed"])
def test_absent_or_changed_remote_staging_ref_is_not_deleted(
    *, source_runner: staging.SourceStagingRunner, remote: str
) -> None:
    inner, journal = source_runner.inner, source_runner.journal
    assert isinstance(inner, _Runner)
    assert isinstance(journal, _Journal)
    inner.remote = remote
    assert _launch(runner=source_runner).exit_code == 0
    assert not any(call[0][:2] == ["git", "push"] for call in inner.calls)
    if remote == "changed":
        assert any("retained on origin" in str(row.get("detail")) for row in journal.records)


@pytest.mark.parametrize(
    "failure",
    [("git", "ls-remote"), ("git", "push"), ("git", "worktree", "remove"), ("git", "update-ref")],
)
def test_cleanup_failure_is_journaled_without_rewriting_the_run_result(
    *, source_runner: staging.SourceStagingRunner, failure: tuple[str, ...]
) -> None:
    inner, journal = source_runner.inner, source_runner.journal
    assert isinstance(inner, _Runner)
    assert isinstance(journal, _Journal)
    inner.fail = failure
    assert _launch(runner=source_runner).exit_code == 0
    failed = [row for row in journal.records if row.get("status") == "failed"]
    assert len(failed) == 1
    assert failed[0]["branch"] == inner.branch
    assert failed[0]["detail"] == "injected failure"
    if failure[-1] == "remove":
        assert not any(call[0][:2] == ["git", "update-ref"] for call in inner.calls)

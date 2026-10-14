"""The staging base in every case the ancestor test does not reach.

Three of these are the arms where the fetched default-branch head does NOT
become the staging base, and the fourth is the refusal that must still land
BEFORE any staging happens. They are together because each one is the same
question answered differently -- which commit the engine's pre-run push will
carry, and whether it may be pushed at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_source_staging as staging
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_refusals import pass_outcome

_HEAD = "a" * 40
_ORIGIN_HEAD = "b" * 40


@dataclass(kw_only=True)
class _Runner:
    origin_head: str = _ORIGIN_HEAD
    fetch_exit: int = 0
    ancestor: bool = True
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
        del cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=self.fetch_exit, stdout="", stderr="fetch refused")
        if argv[:2] == ["git", "rev-parse"]:
            return CommandResult(exit_code=0, stdout=f"{self.origin_head}\n", stderr="")
        if argv[:2] == ["git", "merge-base"]:
            return CommandResult(exit_code=0 if self.ancestor else 1, stdout="", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, repo: Path, root: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-xavjhz",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=root / "janitor",
        default_branch="master",
    )


def _staged(*, runner: _Runner, journal: _Journal, tmp_path: Path) -> CommandResult:
    staging_runner = staging.SourceStagingRunner(
        inner=runner,
        plan=_plan(repo=tmp_path, root=tmp_path),
        journal=journal,
        worktree_root=tmp_path / ".worktrees",
    )
    return staging_runner.run(argv=["fabro", "run"], cwd=tmp_path, timeout_seconds=30)


@pytest.fixture
def proven_head(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        staging,
        "source_checkout_preflight",
        lambda **_: pass_outcome(
            head=_HEAD, origin_refs=("origin/master",), origin_ref="origin/master"
        ),
    )


@pytest.mark.parametrize(
    ("origin_head", "ancestor"),
    [(_ORIGIN_HEAD, True), (_HEAD, True), (_ORIGIN_HEAD, False)],
)
@pytest.mark.usefixtures("proven_head")
def test_only_a_checkout_strictly_behind_origin_stages_at_the_fetched_head(
    *, tmp_path: Path, origin_head: str, ancestor: bool
) -> None:
    runner = _Runner(origin_head=origin_head, ancestor=ancestor)
    assert _staged(runner=runner, journal=_Journal(), tmp_path=tmp_path).exit_code == 0
    added = next(call for call in runner.calls if call[:3] == ["git", "worktree", "add"])
    behind = origin_head != _HEAD and ancestor
    assert added[-1] == (origin_head if behind else _HEAD)


@pytest.mark.parametrize("unobservable", ["fetch-failed", "unreadable-head"])
@pytest.mark.usefixtures("proven_head")
def test_an_unobservable_origin_head_fails_the_staging_closed(
    *, tmp_path: Path, unobservable: str
) -> None:
    runner = _Runner(
        fetch_exit=1 if unobservable == "fetch-failed" else 0,
        origin_head="" if unobservable == "unreadable-head" else _ORIGIN_HEAD,
    )
    journal = _Journal()
    result = _staged(runner=runner, journal=journal, tmp_path=tmp_path)
    assert result.exit_code == 1
    # Nothing is staged on a base nobody could prove current, and no cleanup
    # leg runs against a worktree and a ref that were never created.
    assert not any(call[:2] == ["git", "worktree"] for call in runner.calls)
    assert not any(call[:2] == ["git", "update-ref"] for call in runner.calls)
    staged = next(row for row in journal.records if row["stage"] == "source-checkout-stage")
    assert staged["status"] == "failed"
    assert staged["reason"] == "source-origin-head-unobservable"
    assert staged["terminal"] is True
    if unobservable == "unreadable-head":
        assert "rev-parse FETCH_HEAD" in result.stderr
    else:
        assert result.stderr == "fetch refused"


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(argv=["git", *args], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _source_holding_an_unpushed_commit(*, root: Path) -> Path:
    origin = root / "origin.git"
    repo = root / "source"
    _git(repo=root, args=["init", "--bare", "--initial-branch=master", str(origin)])
    _git(repo=root, args=["init", "--initial-branch=master", str(repo)])
    _git(repo=repo, args=["config", "user.name", "Test User"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["remote", "add", "origin", str(origin)])
    (repo / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(repo=repo, args=["add", "tracked.txt"])
    _git(repo=repo, args=["commit", "-m", "source"])
    _git(repo=repo, args=["push", "origin", "master"])
    (repo / "tracked.txt").write_text("only here\n", encoding="utf-8")
    _git(repo=repo, args=["commit", "-am", "unpublished work"])
    return repo


def test_a_head_no_origin_ref_reaches_is_refused_before_any_staging(*, tmp_path: Path) -> None:
    repo = _source_holding_an_unpushed_commit(root=tmp_path)
    journal = _Journal()
    worktree_root = tmp_path / ".worktrees"
    runner = staging.SourceStagingRunner(
        inner=ShellCommandRunner(),
        plan=_plan(repo=repo, root=tmp_path),
        journal=journal,
        worktree_root=worktree_root,
    )
    result = runner.run(argv=["fabro", "run"], cwd=repo, timeout_seconds=60)
    assert result.exit_code == 3
    assert "not reachable from any origin ref" in result.stderr
    assert "unpublished work" in result.stderr
    assert "fast-forward to its origin tracking ref" in result.stderr
    assert "preserve the unpushed commit(s) on a branch/worktree" in result.stderr
    assert not worktree_root.exists()
    assert not any(row["stage"] == "source-checkout-stage" for row in journal.records)
    assert _git(repo=repo, args=["ls-remote", "--heads", "origin"]).endswith("refs/heads/master")

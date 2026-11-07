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
    origin_url: str = "https://github.com/example/source.git"
    fetch_exit: int = 0
    observed_exit: int = 0
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
        if argv == ["git", "config", "--get", "remote.origin.url"]:
            return CommandResult(exit_code=0, stdout=f"{self.origin_url}\n", stderr="")
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=self.fetch_exit, stdout="", stderr="fetch refused")
        if argv[:2] == ["git", "rev-parse"]:
            return CommandResult(
                exit_code=self.observed_exit,
                stdout=f"{self.origin_head}\n",
                stderr="FETCH_HEAD unreadable",
            )
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
        fabro_version="fabro 0.393.0 (fixture)",
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


@pytest.mark.usefixtures("proven_head")
def test_petri_source_staging_launches_the_proven_remote_default_branch_directly(
    *, tmp_path: Path
) -> None:
    """An explicit target avoids Fabro's client-side push of the disposable branch."""
    runner = _Runner()

    assert _staged(runner=runner, journal=_Journal(), tmp_path=tmp_path).exit_code == 0

    launch = next(call for call in runner.calls if call[:2] == ["fabro", "run"])
    assert launch == ["fabro", "run", "--target", "example/source@master"]


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


@pytest.mark.parametrize(
    ("fetch_exit", "observed_exit", "origin_head", "expected_detail"),
    [
        (0, 0, _HEAD, None),
        (1, 0, _ORIGIN_HEAD, "fetch refused"),
        (0, 0, _ORIGIN_HEAD, f"resolved to {_ORIGIN_HEAD}"),
        (0, 1, _HEAD, "FETCH_HEAD unreadable"),
    ],
)
@pytest.mark.usefixtures("proven_head")
def test_a_resume_stages_only_the_recorded_pull_request_head(
    *,
    tmp_path: Path,
    fetch_exit: int,
    observed_exit: int,
    origin_head: str,
    expected_detail: str | None,
) -> None:
    """A moved or unreadable publication head refuses before Fabro can run."""
    runner = _Runner(
        fetch_exit=fetch_exit,
        observed_exit=observed_exit,
        origin_head=origin_head,
    )
    journal = _Journal()
    plan = _plan(repo=tmp_path, root=tmp_path)
    result = staging.SourceStagingRunner(
        inner=runner,
        plan=plan,
        journal=journal,
        worktree_root=tmp_path / ".worktrees",
        resume_head=_HEAD,
    ).run(argv=["fabro", "run"], cwd=tmp_path, timeout_seconds=30)

    fetch = next(call for call in runner.calls if call[:2] == ["git", "fetch"])
    assert fetch == ["git", "fetch", "--quiet", "origin", plan.branch]
    staged = next(row for row in journal.records if row["stage"] == "source-checkout-stage")
    if expected_detail is None:
        added = next(call for call in runner.calls if call[:3] == ["git", "worktree", "add"])
        assert result.exit_code == 0
        assert added[-1] == _HEAD
        assert staged["status"] == "passed"
        assert staged["staged_at"] == _HEAD
    else:
        assert result.exit_code == 1
        assert expected_detail in result.stderr
        assert _HEAD in result.stderr
        assert not any(call[:2] == ["git", "worktree"] for call in runner.calls)
        assert staged["status"] == "failed"
        assert staged["reason"] == "source-resume-head-unobservable"
        assert staged["terminal"] is True


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(argv=["git", *args], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _source_holding_an_unpushed_commit(*, root: Path, unrelated_ref_count: int = 0) -> Path:
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
    remote_head = _git(repo=repo, args=["rev-parse", "HEAD"])
    for index in range(unrelated_ref_count):
        _git(
            repo=origin,
            args=["update-ref", f"refs/heads/unrelated-{index:04d}", remote_head],
        )
    if unrelated_ref_count:
        _git(repo=repo, args=["fetch", "--quiet", "origin"])
    (repo / "tracked.txt").write_text("only here\n", encoding="utf-8")
    _git(repo=repo, args=["commit", "-am", "unpublished work"])
    return repo


@pytest.mark.parametrize(
    ("unrelated_ref_count", "expected_origin_ref_count", "expected_origin_refs"),
    [
        (0, 1, ("origin/master",)),
        (1_000, 1_001, ("origin/master", "origin/unrelated-0999")),
    ],
)
def test_a_head_no_origin_ref_reaches_is_refused_before_any_staging(
    *,
    tmp_path: Path,
    unrelated_ref_count: int,
    expected_origin_ref_count: int,
    expected_origin_refs: tuple[str, ...],
) -> None:
    repo = _source_holding_an_unpushed_commit(
        root=tmp_path,
        unrelated_ref_count=unrelated_ref_count,
    )
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
    refusal = next(
        row for row in journal.records if row["stage"] == "source-checkout-origin-reachability"
    )
    origin_refs = refusal["origin_refs"]
    assert isinstance(origin_refs, list)
    assert len(origin_refs) == expected_origin_ref_count
    assert set(expected_origin_refs).issubset(origin_refs)
    unpushed_commits = refusal["unpushed_commits"]
    assert isinstance(unpushed_commits, list)
    assert len(unpushed_commits) == 1
    assert "unpublished work" in unpushed_commits[0]
    assert "refs/heads/master" in _git(repo=repo, args=["ls-remote", "--heads", "origin"])

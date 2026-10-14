"""Which commit the staged source branch is created at, over REAL Git.

The checkout this fixture builds is BEHIND origin AND holds a stale
`refs/remotes/origin/master`, which is what makes the two candidate bases
distinguishable: a staging base read from the local tracking ref names the
checkout's own commit, and only a fresh fetch names the head the source branch
must carry. A fixture whose tracking ref was current would pass either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_source_staging as staging
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(argv=["git", *args], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _identified(*, repo: Path) -> None:
    _git(repo=repo, args=["config", "user.name", "Test User"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])


def _behind_source_holding_a_stale_tracking_ref(*, root: Path) -> tuple[Path, str, str]:
    """A checkout one commit behind an origin it has not fetched since."""
    origin = root / "origin.git"
    repo = root / "source"
    peer = root / "peer"
    _git(repo=root, args=["init", "--bare", "--initial-branch=master", str(origin)])
    _git(repo=root, args=["init", "--initial-branch=master", str(repo)])
    _identified(repo=repo)
    _git(repo=repo, args=["remote", "add", "origin", str(origin)])
    (repo / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(repo=repo, args=["add", "tracked.txt"])
    _git(repo=repo, args=["commit", "-m", "source"])
    _git(repo=repo, args=["push", "origin", "master"])
    head = _git(repo=repo, args=["rev-parse", "HEAD"])
    _git(repo=root, args=["clone", str(origin), str(peer)])
    _identified(repo=peer)
    (peer / "tracked.txt").write_text("advanced elsewhere\n", encoding="utf-8")
    _git(repo=peer, args=["commit", "-am", "advance origin"])
    _git(repo=peer, args=["push", "origin", "master"])
    remote_head = _git(repo=peer, args=["rev-parse", "HEAD"])
    assert head != remote_head
    assert _git(repo=repo, args=["rev-parse", "origin/master"]) == head
    return repo, head, remote_head


@dataclass(kw_only=True)
class _EngineRunner:
    """Model only the engine's pre-run push of the staged source branch."""

    launch_heads: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if argv[:2] == ["fabro", "run"]:
            self.launch_heads.append(_git(repo=cwd, args=["rev-parse", "HEAD"]))
            branch = _git(repo=cwd, args=["symbolic-ref", "--short", "HEAD"])
            argv = ["git", "push", "origin", branch]
        return ShellCommandRunner().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )


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


def test_an_ancestor_checkout_stages_at_the_freshly_fetched_default_branch_head(
    *, tmp_path: Path
) -> None:
    repo, head, remote_head = _behind_source_holding_a_stale_tracking_ref(root=tmp_path)
    engine = _EngineRunner()
    runner = staging.SourceStagingRunner(
        inner=engine,
        plan=_plan(repo=repo, root=tmp_path),
        journal=_Journal(),
        worktree_root=tmp_path / ".worktrees",
    )
    result = runner.run(argv=["fabro", "run"], cwd=repo, timeout_seconds=60)
    assert result.exit_code == 0, result.stderr
    # The Red: the source branch carried the checkout's own behind-origin HEAD.
    assert engine.launch_heads == [remote_head]
    # The dispatching checkout itself is never moved, and the staging ref is
    # cleaned up at the commit it was actually staged at.
    assert _git(repo=repo, args=["rev-parse", "HEAD"]) == head
    assert _git(repo=repo, args=["branch", "--format=%(refname:short)"]) == "master"
    assert _git(repo=repo, args=["ls-remote", "--heads", "origin"]) == (
        f"{remote_head}\trefs/heads/master"
    )

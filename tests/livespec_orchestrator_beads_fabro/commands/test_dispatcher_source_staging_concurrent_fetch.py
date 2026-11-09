"""Source staging reads the commit IT fetched, never whatever FETCH_HEAD names last.

`FETCH_HEAD` is one file per checkout, so any other process fetching in the same
checkout between the Dispatcher's fetch and its read of the fetched commit
overwrites the answer. These tests run REAL Git and make that other process act
exactly inside that window: the wrapper below performs a foreign fetch the moment
the Dispatcher's own fetch has returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_source_staging as staging
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan

_FOREIGN_BRANCH = "foreign-tip"
_GUIDANCE_FILE = Path(__file__).resolve().parents[3] / ".ai" / "hosts-and-shell-gotchas.md"


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(argv=["git", *args], cwd=repo, timeout_seconds=30)
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _identified(*, repo: Path) -> None:
    _git(repo=repo, args=["config", "user.name", "Test User"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])


def _commit_file(*, repo: Path, text: str) -> str:
    (repo / "tracked.txt").write_text(f"{text}\n", encoding="utf-8")
    _git(repo=repo, args=["add", "tracked.txt"])
    _git(repo=repo, args=["commit", "-m", text])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


@dataclass(frozen=True, kw_only=True)
class _World:
    repo: Path
    plan: DispatchPlan
    head: str
    master_tip: str
    publish_tip: str
    foreign_tip: str


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, repo: Path, root: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-ysgz56",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=root / "janitor",
        default_branch="master",
    )


def _world(*, root: Path) -> _World:
    """A checkout one commit behind origin, with a publish branch and a foreign branch."""
    origin = root / "origin.git"
    repo = root / "source"
    peer = root / "peer"
    plan = _plan(repo=repo, root=root)
    _git(repo=root, args=["init", "--bare", "--initial-branch=master", str(origin)])
    _git(repo=root, args=["init", "--initial-branch=master", str(repo)])
    _identified(repo=repo)
    _git(repo=repo, args=["remote", "add", "origin", str(origin)])
    head = _commit_file(repo=repo, text="source")
    _git(repo=repo, args=["push", "origin", "master"])
    _git(repo=root, args=["clone", str(origin), str(peer)])
    _identified(repo=peer)
    _git(repo=peer, args=["checkout", "-b", plan.branch])
    publish_tip = _commit_file(repo=peer, text="published work")
    _git(repo=peer, args=["push", "origin", plan.branch])
    _git(repo=peer, args=["checkout", "-b", _FOREIGN_BRANCH, "master"])
    foreign_tip = _commit_file(repo=peer, text="another seat's branch")
    _git(repo=peer, args=["push", "origin", _FOREIGN_BRANCH])
    _git(repo=peer, args=["checkout", "master"])
    master_tip = _commit_file(repo=peer, text="advance origin")
    _git(repo=peer, args=["push", "origin", "master"])
    assert len({head, publish_tip, foreign_tip, master_tip}) == 4
    return _World(
        repo=repo,
        plan=plan,
        head=head,
        master_tip=master_tip,
        publish_tip=publish_tip,
        foreign_tip=foreign_tip,
    )


@dataclass(kw_only=True)
class _RacingRunner:
    """Real Git, plus another process fetching in the same checkout after each Dispatcher fetch."""

    repo: Path
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
            return CommandResult(exit_code=0, stdout="", stderr="")
        result = ShellCommandRunner().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )
        if argv[:2] == ["git", "fetch"] and result.exit_code == 0:
            _git(repo=self.repo, args=["fetch", "--quiet", "origin", _FOREIGN_BRANCH])
        return result


def _stage(
    *, world: _World, root: Path, resume_head: str | None
) -> tuple[CommandResult, list[str]]:
    engine = _RacingRunner(repo=world.repo)
    runner = staging.SourceStagingRunner(
        inner=engine,
        plan=world.plan,
        journal=_Journal(),
        worktree_root=root / ".worktrees",
        resume_head=resume_head,
    )
    result = runner.run(argv=["fabro", "run"], cwd=world.repo, timeout_seconds=60)
    return result, engine.launch_heads


def test_a_resume_anchors_on_its_recorded_head_despite_a_foreign_fetch(*, tmp_path: Path) -> None:
    world = _world(root=tmp_path)
    result, launch_heads = _stage(world=world, root=tmp_path, resume_head=world.publish_tip)
    assert result.exit_code == 0, result.stderr
    assert launch_heads == [world.publish_tip]


def test_a_resume_whose_publish_head_moved_still_refuses_naming_both_heads(
    *, tmp_path: Path
) -> None:
    world = _world(root=tmp_path)
    result, launch_heads = _stage(world=world, root=tmp_path, resume_head=world.head)
    assert result.exit_code == 1
    assert world.head in result.stderr
    assert world.publish_tip in result.stderr
    assert launch_heads == []


def test_a_plain_dispatch_stages_at_the_default_branch_head_despite_a_foreign_fetch(
    *, tmp_path: Path
) -> None:
    world = _world(root=tmp_path)
    result, launch_heads = _stage(world=world, root=tmp_path, resume_head=None)
    assert result.exit_code == 0, result.stderr
    assert launch_heads == [world.master_tip]
    assert world.foreign_tip != world.master_tip


def test_repeated_dispatches_leave_no_new_ref_in_the_staging_checkout(*, tmp_path: Path) -> None:
    world = _world(root=tmp_path)
    _git(repo=world.repo, args=["fetch", "--quiet", "origin"])
    refs_before = _git(repo=world.repo, args=["for-each-ref", "--format=%(refname)"])
    for resume_head in (None, world.publish_tip, None):
        result, _ = _stage(world=world, root=tmp_path, resume_head=resume_head)
        assert result.exit_code == 0, result.stderr
    assert _git(repo=world.repo, args=["for-each-ref", "--format=%(refname)"]) == refs_before


def test_the_host_guidance_forbids_fetching_in_a_shared_primary_checkout() -> None:
    text = " ".join(_GUIDANCE_FILE.read_text(encoding="utf-8").split())
    assert "never run `git fetch` in a shared primary checkout" in text.lower()
    assert "`git ls-remote`" in text
    assert "scratch clone" in text

"""Binds Scenario 236 — the staged source checkout's worktree and branch names.

The names are a STABLE INTERFACE rather than an implementation detail, which is
why they are worth a test of their own: livespec-dev-tooling's reap-safety clause
treats a worktree named `fabro-source-<id>` as factory-owned and never removes
it, so a rename here silently retires that protection — the reaper keeps
answering, keeps exiting zero, and starts deleting live factory checkouts.

The staging runs for REAL, against a real Git repository with a real origin, and
only the engine launch is stood in: the directory and the branch are read off the
checkout the runner actually created, at the one moment it exists, because
`_cleanup` removes both as soon as the launch returns.

Three properties of this module an editor must not invert.

The repository directory is named `governed-repo` and the assertion compares the
staged checkout's parent against `repo.name`, never against that literal. The
clause is that the parent is named after the DISPATCHING REPOSITORY's checkout
directory, and a fixture whose expectation is spelled independently of the
repository would pass just as well against a runner that hardcoded one name, or
one that used the work-item id — and the second is the plausible wrong answer,
since the work-item id is the other identifier in scope.

The branch's 32 characters are EXTRACTED from the directory name rather than
matched by a second regex of their own. The clause ties the two names to one
identifier, so two independent shape assertions are satisfied by a runner that
mints a fresh id per name — which is the defect that defeats the reaper from the
other direction, since a reaper recognising the worktree can no longer name the
branch it belongs to.

And the publish branch is read off the PLAN rather than transcribed, so the
not-the-publish-branch assertion keeps meaning what it says if the publish
branch's own derivation changes; a transcribed `feat/<id>` would quietly stop
being a comparison against anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_staging import (
    SourceStagingRunner,
)

# The ratified worktree name: the fixed prefix plus exactly 32 lowercase
# hexadecimal characters. The capture is what ties the branch to this directory.
_STAGED_WORKTREE_NAME = re.compile(r"^fabro-source-([0-9a-f]{32})$")

_STAGED_BRANCH_PREFIX = "livespec/source/"

# A name nothing in the Dispatcher could compose for itself, so "the parent is
# named after the repository's checkout directory" can actually fail.
_REPOSITORY_DIRECTORY = "governed-repo"

_WORK_ITEM_ID = "bd-ib-7pags"

_GIT_TIMEOUT_SECONDS = 30.0


def _git(*, repo: Path, args: list[str]) -> str:
    result = ShellCommandRunner().run(
        argv=["git", *args], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS
    )
    assert result.exit_code == 0, result.stderr
    return result.stdout.strip()


def _governed_repository(*, root: Path) -> Path:
    """A real checkout whose HEAD an `origin/*` ref contains, so staging proceeds."""
    origin = root / "origin.git"
    repo = root / _REPOSITORY_DIRECTORY
    _git(repo=root, args=["init", "--bare", str(origin)])
    _git(repo=root, args=["init", "--initial-branch=master", str(repo)])
    _git(repo=repo, args=["config", "user.name", "Test User"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["remote", "add", "origin", str(origin)])
    (repo / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(repo=repo, args=["add", "tracked.txt"])
    _git(repo=repo, args=["commit", "-m", "source"])
    _git(repo=repo, args=["push", "origin", "master"])
    return repo


@dataclass(kw_only=True)
class _LaunchObserver:
    """Stand in for the engine launch ALONE; every other argv is real Git.

    The checkout and its branch are read INSIDE the launch because the runner's
    cleanup removes the worktree and deletes the branch the moment the launch
    returns, so nothing observable afterwards can answer either question.
    """

    checkouts: list[Path] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)

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
            self.checkouts.append(cwd)
            self.branches.append(_git(repo=cwd, args=["symbolic-ref", "--short", "HEAD"]))
            return CommandResult(exit_code=0, stdout="", stderr="")
        return ShellCommandRunner().run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_scenario236_the_staged_source_checkout_carries_the_ratified_names(
    *, tmp_path: Path
) -> None:
    repo = _governed_repository(root=tmp_path)
    engine = _LaunchObserver()
    journal = _Journal()
    worktree_root = tmp_path / ".worktrees"
    plan = build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
        default_branch="master",
    )
    runner = SourceStagingRunner(
        inner=engine, plan=plan, journal=journal, worktree_root=worktree_root
    )

    result = runner.run(argv=["fabro", "run"], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS)

    assert result.exit_code == 0, result.stderr
    # One staged launch, so every name below is read off the checkout the runner
    # created rather than off whichever of several a later assertion happened to
    # pick up.
    assert len(engine.checkouts) == 1
    checkout = engine.checkouts[0]
    staged_branch = engine.branches[0]

    # Assertion 1 — the directory is the ratified name.
    staged_name = _STAGED_WORKTREE_NAME.match(checkout.name)
    assert staged_name is not None, checkout.name
    identifier = staged_name.group(1)

    # Assertion 2 — its parent is the dispatching repository's own checkout
    # directory, under the worktree root the runner was given.
    assert checkout.parent == worktree_root / repo.name

    # Assertion 3 — the branch carries the SAME 32 characters, and is a local
    # branch of the staged checkout rather than the run's publish branch.
    assert staged_branch == f"{_STAGED_BRANCH_PREFIX}{identifier}"
    assert staged_branch != plan.branch

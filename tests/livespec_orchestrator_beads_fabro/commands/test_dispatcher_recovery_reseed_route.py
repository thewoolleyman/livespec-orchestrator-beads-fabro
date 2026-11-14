"""A seeded recovery route is reseeded onto the default branch before its run starts.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A seed is moved onto the
current default branch before its run starts" and "A stale seed is re-seeded by
diff-applying its work onto the default branch's tip"; Scenario 348.

EVERY CASE RUNS REAL GIT AGAINST A LOCAL BARE ORIGIN. The reseed is a sequence of
git commands whose OUTPUT decides each next one (the merge base, the trees, the
unmerged paths), so a scripted shell would assert the order of calls and prove
nothing about the tree the run starts from. The failure cases wrap the real
runner and fail one named command, which is how each unobservable arm is reached.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    journal_recovery_route,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_reseed_route import (
    DefaultBranchTipReader,
    reseed_route,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_RESUME,
    ROUTE_SEEDED,
    RecoveryRoute,
    RecoverySeed,
)

_ITEM = "bd-ib-zzhy5t"
_RUN = "01M6PC4XKRYVCGZQ9H1GSZA89E"
_SEED_REF = f"refs/heads/needs-human/{_RUN}"
_RESEED_PREFIX = f"refs/livespec/reseed/{_ITEM}/"
_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**_IDENTITY, "PATH": os.environ["PATH"], "HOME": str(cwd)},
    )
    return done.stdout.strip()


def _commit(*, work: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        _ = (work / name).write_text(text, encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-q", "--allow-empty", "-m", message, cwd=work)
    return _git("rev-parse", "HEAD", cwd=work)


@dataclass(kw_only=True)
class _World:
    root: Path
    origin: Path
    repo: Path
    work: Path
    base: str
    tip: str


def _world(*, tmp_path: Path) -> _World:
    """A bare origin whose main moved past the commit a seed branched from."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    _git("clone", "-q", str(origin), str(work), cwd=tmp_path)
    _git("checkout", "-q", "-b", "main", cwd=work)
    base = _commit(
        work=work,
        files={"a.txt": "a1\na2\na3\n", "b.txt": "b1\nb2\nb3\n", "c.txt": "c\n"},
        message="base",
    )
    _git("push", "-q", "origin", "main", cwd=work)
    tip = _commit(work=work, files={"b.txt": "b1\nB2 on main\nb3\n"}, message="main moves")
    _git("push", "-q", "origin", "main", cwd=work)
    repo = tmp_path / "repo"
    _git("clone", "-q", str(origin), str(repo), cwd=tmp_path)
    return _World(root=tmp_path, origin=origin, repo=repo, work=work, base=base, tip=tip)


def _publish_seed(*, world: _World, files: dict[str, str], parent: str) -> str:
    _git("checkout", "-q", "--detach", parent, cwd=world.work)
    commit = _commit(work=world.work, files=files, message="the preserved work")
    _git("push", "-q", "origin", f"{commit}:{_SEED_REF}", cwd=world.work)
    return commit


def _route(*, commit: str) -> RecoveryRoute:
    return RecoveryRoute(
        work_item_id=_ITEM,
        route=ROUTE_SEEDED,
        seed=RecoverySeed(
            source_run_id=_RUN,
            remote="origin",
            commit_sha=commit,
            preservation_ref=_SEED_REF,
        ),
        preserved_work="verified",
    )


def _reseed(
    *,
    world: _World,
    route: RecoveryRoute,
    runner: Any = None,
    reader: DefaultBranchTipReader | None = None,
) -> tuple[RecoveryRoute, JournalFile]:
    journal = JournalFile(path=world.root / "journal.jsonl")
    routed = reseed_route(
        route=route,
        tip_reader=reader or DefaultBranchTipReader(),
        runner=runner or ShellCommandRunner(),
        repo=world.repo,
        journal=journal,
    )
    return routed, journal


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    if not journal.path.exists():
        return []
    written = (json.loads(line) for line in journal.path.read_text("utf-8").splitlines() if line)
    return [row for row in written if row.get("stage") == stage]


def _origin_refs(*, world: _World, pattern: str) -> str:
    return _git("for-each-ref", "--format=%(objectname) %(refname)", pattern, cwd=world.origin)


def test_a_stale_seed_is_reseeded_onto_the_tip_and_published_before_the_run(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.base
    )

    routed, journal = _reseed(world=world, route=_route(commit=seed_commit))

    seed = routed.seed
    assert routed.route == ROUTE_SEEDED
    assert seed is not None
    assert seed.commit_sha != seed_commit
    reseed_ref = f"{_RESEED_PREFIX}{seed.commit_sha}"
    assert seed.preservation_ref == reseed_ref
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX) == f"{seed.commit_sha} {reseed_ref}"
    _git("fetch", "-q", "origin", reseed_ref, cwd=world.repo)
    assert _git("rev-list", "--parents", "-n", "1", seed.commit_sha, cwd=world.repo) == (
        f"{seed.commit_sha} {world.tip}"
    )
    assert _git("show", f"{seed.commit_sha}:a.txt", cwd=world.repo) == "a1\nA2 seed\na3"
    assert _git("show", f"{seed.commit_sha}:b.txt", cwd=world.repo) == "b1\nB2 on main\nb3"
    assert (seed.source_ref, seed.source_commit, seed.default_branch_tip) == (
        _SEED_REF,
        seed_commit,
        world.tip,
    )
    assert seed.source_run_id == _RUN
    assert _origin_refs(world=world, pattern=_SEED_REF) == f"{seed_commit} {_SEED_REF}"
    body = _git("log", "-1", "--format=%B", seed.commit_sha, cwd=world.repo)
    assert body.splitlines()[0] == f"reseed {_ITEM} from {_SEED_REF} onto main"
    assert f"Livespec-Reseed-Source: {_SEED_REF} {seed_commit}" in body
    assert f"Livespec-Reseed-Onto: {world.tip}" in body
    journal_recovery_route(route=routed, journal=journal)
    (row,) = _rows(journal=journal, stage="recovery-route")
    assert (row["commit_sha"], row["preservation_ref"]) == (seed.commit_sha, reseed_ref)
    assert (row["seed_source_ref"], row["seed_source_commit"], row["default_branch_tip"]) == (
        _SEED_REF,
        seed_commit,
        world.tip,
    )


def test_reseeding_one_seed_onto_one_tip_twice_records_the_same_commit_and_one_ref(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.base
    )

    first, _ = _reseed(world=world, route=_route(commit=seed_commit))
    second, _ = _reseed(world=world, route=_route(commit=seed_commit))

    assert first.seed is not None
    assert second.seed is not None
    assert second.seed.commit_sha == first.seed.commit_sha
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX).count("\n") == 0
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX) != ""


def test_a_reseed_conflict_holds_the_item_naming_every_conflicting_path(tmp_path: Path) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world,
        files={"b.txt": "b1\nB2 on the seed\nb3\n", "a.txt": "a1\na2\na3\nmore\n"},
        parent=world.base,
    )
    _git("checkout", "-q", "main", cwd=world.work)
    _ = _commit(work=world.work, files={"a.txt": "a1\na2\na3\nclash\n"}, message="main edits a too")
    _git("push", "-q", "origin", "main", cwd=world.work)

    routed, journal = _reseed(world=world, route=_route(commit=seed_commit))

    tip = _git("rev-parse", "refs/heads/main", cwd=world.origin)
    assert routed.route == ROUTE_HELD
    assert routed.seed is None
    hold = routed.hold
    assert hold is not None
    assert hold.refusals == ("seed-reseed-conflict",)
    conflict = hold.reseed_conflict
    assert conflict is not None
    assert (conflict.seed_ref, conflict.seed_commit, conflict.default_branch_tip) == (
        _SEED_REF,
        seed_commit,
        tip,
    )
    assert conflict.paths == ("a.txt", "b.txt")
    (row,) = _rows(journal=journal, stage="recovery-held")
    assert row["refusals"] == ["seed-reseed-conflict"]
    assert (row["seed_ref"], row["seed_commit"], row["default_branch_tip"]) == (
        _SEED_REF,
        seed_commit,
        tip,
    )
    assert row["conflicting_paths"] == ["a.txt", "b.txt"]
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX) == ""
    assert _origin_refs(world=world, pattern=_SEED_REF) == f"{seed_commit} {_SEED_REF}"


def test_a_seed_carrying_no_work_routes_fresh_and_is_listed_as_passed_over(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(world=world, files={}, parent=world.base)

    routed, journal = _reseed(world=world, route=_route(commit=seed_commit))

    assert routed.route == ROUTE_FRESH
    assert routed.seed is None
    journal_recovery_route(route=routed, journal=journal)
    (row,) = _rows(journal=journal, stage="recovery-route")
    assert row["route"] == ROUTE_FRESH
    assert {"ref": _SEED_REF, "commit": seed_commit, "reason": "no-change"} in row[
        "passed_over_needs_human"
    ]
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX) == ""


def test_a_seed_already_on_the_tip_is_used_unchanged_and_nothing_is_published(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.tip)
    route = _route(commit=seed_commit)

    routed, journal = _reseed(world=world, route=route)

    assert routed == route
    assert _origin_refs(world=world, pattern=_RESEED_PREFIX) == ""
    assert _rows(journal=journal, stage="recovery-held") == []


@pytest.mark.parametrize("kept", [ROUTE_FRESH, ROUTE_RESUME])
def test_a_route_that_is_not_seeded_is_returned_untouched(tmp_path: Path, kept: str) -> None:
    world = _world(tmp_path=tmp_path)
    route = RecoveryRoute(work_item_id=_ITEM, route=kept)

    routed, _journal = _reseed(world=world, route=route)

    assert routed is route


def test_the_tip_is_read_once_for_every_item_the_pass_routes(tmp_path: Path) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.base
    )
    reads: list[str] = []

    class _Counting(ShellCommandRunner):
        def run(self, **kwargs: Any) -> CommandResult:
            joined = " ".join(kwargs["argv"])
            if "ls-remote" in joined and "refs/heads/main" in joined:
                reads.append(joined)
            return super().run(**kwargs)

    reader = DefaultBranchTipReader()
    route = _route(commit=seed_commit)
    first, _ = _reseed(world=world, route=route, runner=_Counting(), reader=reader)
    second, _ = _reseed(world=world, route=route, runner=_Counting(), reader=reader)

    assert first.seed is not None
    assert second.seed is not None
    assert first.seed.commit_sha == second.seed.commit_sha
    assert len(reads) == 1


class _Failing(ShellCommandRunner):
    """The real runner, except the commands whose argv holds every needle fail.

    A needle may name alternatives with `|`: the suite's `gh` stand-in answers the
    default-branch query with `main`, so the unresolvable case must fail BOTH routes
    of the ratified two-route resolution rather than only the git one.
    """

    def __init__(self, *, needles: tuple[str, ...], exit_code: int = 1) -> None:
        self._needles = needles
        self._answer = CommandResult(exit_code=exit_code, stdout="", stderr="refused")

    def run(self, **kwargs: Any) -> CommandResult:
        joined = " ".join(kwargs["argv"])
        if all(any(part in joined for part in needle.split("|")) for needle in self._needles):
            return self._answer
        return super().run(**kwargs)


@pytest.mark.parametrize(
    "needles",
    [
        pytest.param(("symbolic-ref|defaultBranchRef",), id="default-branch-unresolvable"),
        pytest.param(("ls-remote", "refs/heads/main"), id="tip-unreadable"),
        pytest.param(("fetch",), id="fetch-fails"),
        pytest.param(("merge-base",), id="no-merge-base"),
        pytest.param(("checkout",), id="checkout-fails"),
        pytest.param(("apply",), id="apply-fails-without-a-conflict"),
        pytest.param(("commit-tree",), id="commit-fails"),
        pytest.param(("push",), id="publication-fails"),
    ],
)
def test_a_reseed_that_cannot_be_read_or_attempted_is_an_unobservable_hold(
    tmp_path: Path, needles: tuple[str, ...]
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.base
    )
    runner = _Failing(needles=needles)

    routed, journal = _reseed(world=world, route=_route(commit=seed_commit), runner=runner)

    assert routed.route == ROUTE_HELD
    hold = routed.hold
    assert hold is not None
    assert hold.refusals == ()
    assert hold.reseed_conflict is None
    assert [one.name for one in hold.measurements] == ["seed-reseed"]
    (row,) = _rows(journal=journal, stage="recovery-held")
    assert row["measurements"] == ["seed-reseed"]
    assert _origin_refs(world=world, pattern=_SEED_REF) == f"{seed_commit} {_SEED_REF}"


@pytest.mark.parametrize(
    "needles",
    [
        pytest.param(("ls-remote", "refs/heads/main"), id="tip-missing"),
        pytest.param(("ls-remote", "livespec/reseed"), id="publication-not-confirmed"),
    ],
)
def test_an_empty_answer_is_never_read_as_a_tip_or_a_confirmation(
    tmp_path: Path, needles: tuple[str, ...]
) -> None:
    world = _world(tmp_path=tmp_path)
    seed_commit = _publish_seed(
        world=world, files={"a.txt": "a1\nA2 seed\na3\n"}, parent=world.base
    )
    runner = _Failing(needles=needles, exit_code=0)

    routed, _journal = _reseed(world=world, route=_route(commit=seed_commit), runner=runner)

    assert routed.route == ROUTE_HELD
    assert routed.seed is None
    assert routed.hold is not None
    assert [one.name for one in routed.hold.measurements] == ["seed-reseed"]

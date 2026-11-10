"""Whether a pull request's head moved from its proved head only in its commit message.

`_drive_merge_hold_arm_guard` compares the pull request's CURRENT head against
the head the latest `verified` or `carried_forward` record names. Equality is the
ordinary answer; this answers the one other case the ratified clause admits: the
two commits are distinct, each has exactly one parent, that parent is the same
commit, and their trees are the same tree object. A proof graded a TREE, and a
commit that carries the same tree on the same parent under a reworded message
changes nothing the proof measured -- the measured instance was a hand reword of
a factory commit that had no subject, which moved the head and refused the
release for want of a record naming the new one.

Both commits are read through the forge's git-data endpoint, by the runner the
guard already holds, because the current head is a commit the release host may
never have fetched and a local `git cat-file` would answer "missing" for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = ["HeadRefusal", "SharedTree", "compare_heads"]

_COMMIT_ENDPOINT = "/repos/{owner}/{repo}/git/commits"
_COMMIT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _Commit:
    tree: str
    parents: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class SharedTree:
    """The comparison found the move message-only: both heads carry this tree."""

    tree: str


@dataclass(frozen=True, kw_only=True)
class HeadRefusal:
    """The comparison refused the move, naming the measurement that failed."""

    measurement: str


def compare_heads(
    *, repo: Path, proved: str, current: str, runner: CommandRunner
) -> SharedTree | HeadRefusal:
    """Compare `current` with `proved`, reading both commits through the forge.

    The measurements are taken in the order the clause names them: the two reads,
    then the TREE, then the PARENT. The tree comes first because it is the one
    the proof graded; a head carrying another tree is refused as such whatever
    its history, and the parent comparison is named only when the trees matched.
    """
    proved_commit = _read_commit(repo=repo, sha=proved, runner=runner)
    if isinstance(proved_commit, HeadRefusal):
        return proved_commit
    current_commit = _read_commit(repo=repo, sha=current, runner=runner)
    if isinstance(current_commit, HeadRefusal):
        return current_commit
    if proved_commit.tree != current_commit.tree:
        return HeadRefusal(
            measurement=(
                f"the tree comparison failed: {proved} carries tree {proved_commit.tree} "
                f"but {current} carries tree {current_commit.tree}"
            )
        )
    if len(proved_commit.parents) != 1 or proved_commit.parents != current_commit.parents:
        return HeadRefusal(
            measurement=(
                f"the parent comparison failed: {proved} has parents "
                f"[{', '.join(proved_commit.parents)}] but {current} has parents "
                f"[{', '.join(current_commit.parents)}], and a message-only move needs both "
                "to have exactly one parent, the same commit"
            )
        )
    return SharedTree(tree=proved_commit.tree)


def _read_commit(*, repo: Path, sha: str, runner: CommandRunner) -> _Commit | HeadRefusal:
    answered = runner.run(
        argv=["gh", "api", f"{_COMMIT_ENDPOINT}/{sha}"],
        cwd=repo,
        timeout_seconds=_COMMIT_TIMEOUT_SECONDS,
    )
    if answered.exit_code != 0:
        return _unread(sha=sha, why=f"the forge answered with exit {answered.exit_code}")
    parsed = parse_json(text=answered.stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return _unread(sha=sha, why="the forge's answer is not a commit object")
    payload = cast("dict[str, object]", parsed)
    tree = _sha_of(node=payload.get("tree"))
    raw_parents = payload.get("parents")
    if tree is None or not isinstance(raw_parents, list):
        return _unread(sha=sha, why="the commit object carries no readable tree or parents")
    parents = tuple(_sha_of(node=one) for one in cast("list[object]", raw_parents))
    if any(one is None for one in parents):
        return _unread(sha=sha, why="a parent of the commit object carries no readable sha")
    return _Commit(tree=tree, parents=cast("tuple[str, ...]", parents))


def _unread(*, sha: str, why: str) -> HeadRefusal:
    return HeadRefusal(measurement=f"the read of commit {sha} through the forge failed: {why}")


def _sha_of(*, node: object) -> str | None:
    """The `sha` of one `{"sha": ...}` object, or `None` for any other shape."""
    if not isinstance(node, dict):
        return None
    sha = cast("dict[str, object]", node).get("sha")
    return sha if isinstance(sha, str) and sha else None

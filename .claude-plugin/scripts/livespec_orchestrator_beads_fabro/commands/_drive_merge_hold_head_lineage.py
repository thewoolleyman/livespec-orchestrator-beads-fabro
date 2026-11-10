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

__all__: list[str] = ["HeadComparison", "compare_heads"]

_COMMIT_ENDPOINT = "/repos/{owner}/{repo}/git/commits"
_COMMIT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _Commit:
    tree: str
    parents: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class HeadComparison:
    """What comparing the proved head with the current head showed.

    `tree` is set when the move is message-only. `failed` is set when a
    measurement REFUSED the move and names it. Neither is set when the move is
    not shown to be message-only and no measurement can be named.
    """

    tree: str | None = None
    failed: str | None = None


def compare_heads(
    *, repo: Path, proved: str, current: str, runner: CommandRunner
) -> HeadComparison:
    """Compare `current` with `proved`, reading both commits through the forge."""
    proved_commit = _read_commit(repo=repo, sha=proved, runner=runner)
    current_commit = _read_commit(repo=repo, sha=current, runner=runner)
    if proved_commit is None or current_commit is None:
        return HeadComparison()
    if proved_commit.tree != current_commit.tree:
        return HeadComparison(
            failed=(
                f"the tree comparison failed: {proved} carries tree {proved_commit.tree} "
                f"but {current} carries tree {current_commit.tree}"
            )
        )
    if len(proved_commit.parents) != 1 or proved_commit.parents != current_commit.parents:
        return HeadComparison()
    return HeadComparison(tree=proved_commit.tree)


def _read_commit(*, repo: Path, sha: str, runner: CommandRunner) -> _Commit | None:
    answered = runner.run(
        argv=["gh", "api", f"{_COMMIT_ENDPOINT}/{sha}"],
        cwd=repo,
        timeout_seconds=_COMMIT_TIMEOUT_SECONDS,
    )
    if answered.exit_code != 0:
        return None
    parsed = parse_json(text=answered.stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    payload = cast("dict[str, object]", parsed)
    tree = _sha_of(node=payload.get("tree"))
    raw_parents = payload.get("parents")
    if tree is None or not isinstance(raw_parents, list):
        return None
    parents = tuple(_sha_of(node=one) for one in cast("list[object]", raw_parents))
    if any(one is None for one in parents):
        return None
    return _Commit(tree=tree, parents=cast("tuple[str, ...]", parents))


def _sha_of(*, node: object) -> str | None:
    """The `sha` of one `{"sha": ...}` object, or `None` for any other shape."""
    if not isinstance(node, dict):
        return None
    sha = cast("dict[str, object]", node).get("sha")
    return sha if isinstance(sha, str) and sha else None

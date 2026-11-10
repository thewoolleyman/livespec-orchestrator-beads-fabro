"""The governed spec tree's H2 headings, read from the target repository's default branch.

WHY THE WALL DOES NOT READ THE PRIMARY CHECKOUT (work-item bd-ib-ahtcng). The
Definition-of-Done wall used to read `<repo>/SPECIFICATION` from the working tree.
A primary checkout is auto-pulled, so it lags after any merge burst: measured
2026-11-09 on livespec-driver-codex, the wall refused a References heading that
had been on the remote default branch since revise v022, because the primary sat three
commits behind. Any item filed against a just-merged revise could be refused the
same way, and the refusal text named a heading that was perfectly valid.

So the heading set is read from the remote revision: fetch the resolved default
branch first,
then read the tree out of that ref with `git ls-tree` and `git show`, never from
the working tree. The filing display and the dispatch-time wall both reach this
read through `definition_of_done_findings`, so they resolve against ONE revision.

WHY AN UNREADABLE REMOTE IS A VALUE, NOT AN EMPTY SET. The previous reader
returned an empty set for "could not read" and the caller skipped the reference
check, on the reasoning that an environment fault must not refuse every item.
That reasoning protected a read of a local directory, which can only fail for a
local reason. Judging against the primary checkout when the remote cannot be read
is exactly the stale read this module exists to remove, so an unreadable remote
revision is returned as `OriginSpecUnreadable`, carrying what failed, and the
caller refuses the item and names it. A readable tree that carries no heading is
a different answer — an empty set — and every reference is then unresolved.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import child_env
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "OriginSpecUnreadable",
    "origin_spec_h2_headings",
]

_CANONICAL_BRANCH_KEY = "canonical_branch"
_ORIGIN_HEAD_REVISION = "origin/HEAD"
# The governed spec tree's directory name, as the repository layout fixes it.
_SPEC_DIRNAME = "SPECIFICATION"
# Only the tree's OWN top-level files. `history/` and `proposed_changes/` are
# deliberately out: a reference must name a heading of the CURRENT ratified spec,
# and admitting a historical snapshot's headings would let a reference resolve
# against a clause that has since been replaced.
_TOP_LEVEL_SPEC_FILE = re.compile(rf"^{_SPEC_DIRNAME}/[^/]+\.md$")
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_GIT_TIMEOUT_SECONDS = 120.0
# The ambient repository selectors a caller's own git invocation (a commit hook,
# for one) exports. The wall asks about the repository at `cwd`, so none of them
# may redirect the read to another repository.
_AMBIENT_GIT_SELECTORS: dict[str, str | None] = {
    "GIT_DIR": None,
    "GIT_WORK_TREE": None,
    "GIT_INDEX_FILE": None,
    "GIT_COMMON_DIR": None,
    "GIT_OBJECT_DIRECTORY": None,
    "GIT_PREFIX": None,
}


@dataclass(frozen=True, kw_only=True)
class OriginSpecUnreadable:
    """The remote revision could not be read; `detail` says which git step failed."""

    detail: str
    revision: str = _ORIGIN_HEAD_REVISION


@dataclass(frozen=True, kw_only=True)
class _OriginSpecRefs:
    """The three spellings Git needs for one resolved branch."""

    revision: str
    remote_ref: str
    fetch_refspec: str


def origin_spec_h2_headings(*, repo: Path) -> frozenset[str] | OriginSpecUnreadable:
    """The H2 headings of the default branch's governed spec tree, or why it is unreadable.

    Each heading enters the set as its verbatim `## <title>` line. A reference
    must carry that marker as well as the heading text, so the filing-time wall
    agrees with the Definition-of-Done rubric before an item can consume a
    dispatch slot.
    """
    refs = _origin_spec_refs(repo=repo)
    fetched = _git(repo=repo, argv=["fetch", "--quiet", "origin", refs.fetch_refspec])
    if isinstance(fetched, OriginSpecUnreadable):
        return _at_revision(unreadable=fetched, revision=refs.revision)
    listing = _git(repo=repo, argv=["ls-tree", "--name-only", refs.remote_ref, f"{_SPEC_DIRNAME}/"])
    if isinstance(listing, OriginSpecUnreadable):
        return _at_revision(unreadable=listing, revision=refs.revision)
    headings: set[str] = set()
    for path in sorted(line for line in listing.splitlines() if _TOP_LEVEL_SPEC_FILE.match(line)):
        text = _git(repo=repo, argv=["show", f"{refs.remote_ref}:{path}"])
        if isinstance(text, OriginSpecUnreadable):
            return _at_revision(unreadable=text, revision=refs.revision)
        for raw in text.splitlines():
            match = _H2.match(raw)
            if match is not None:
                headings.add(f"## {match.group(1)}")
    return frozenset(headings)


def _origin_spec_refs(*, repo: Path) -> _OriginSpecRefs:
    """The refs for the declared canonical branch, else the remote's HEAD branch."""
    branch = _canonical_branch(repo=repo)
    if branch is None:
        remote_head = _git(
            repo=repo,
            argv=["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        )
        if isinstance(remote_head, str):
            branch = remote_head.strip().removeprefix("origin/") or None
        if branch is None:
            return _OriginSpecRefs(
                revision=_ORIGIN_HEAD_REVISION,
                remote_ref="refs/remotes/origin/HEAD",
                fetch_refspec="+HEAD:refs/remotes/origin/HEAD",
            )
    revision = f"origin/{branch}"
    remote_ref = f"refs/remotes/{revision}"
    return _OriginSpecRefs(
        revision=revision,
        remote_ref=remote_ref,
        fetch_refspec=f"+refs/heads/{branch}:{remote_ref}",
    )


def _canonical_branch(*, repo: Path) -> str | None:
    """The declared canonical branch, when the governed repository names one."""
    config = repo / ".livespec.jsonc"
    if not config.exists():
        return None
    parsed = _jsonc.parse(text=config.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        return None
    branch = cast("dict[str, object]", parsed).get(_CANONICAL_BRANCH_KEY)
    return branch.strip() if isinstance(branch, str) and branch.strip() else None


def _at_revision(*, unreadable: OriginSpecUnreadable, revision: str) -> OriginSpecUnreadable:
    return OriginSpecUnreadable(detail=unreadable.detail, revision=revision)


def _git(*, repo: Path, argv: list[str]) -> str | OriginSpecUnreadable:
    """One git read in `repo`: its standard output, or what made it unreadable."""
    completed = attempt(
        action=lambda: subprocess.run(  # noqa: S603 - fixed argv, never a shell
            ["git", "-C", str(repo), *argv],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=child_env(delta=_AMBIENT_GIT_SELECTORS),
        ),
        exceptions=(OSError, subprocess.SubprocessError),
    )
    if isinstance(completed, AttemptFailure):
        return OriginSpecUnreadable(detail=f"`git {argv[0]}` could not run: {completed.error}")
    if completed.returncode != 0:
        return OriginSpecUnreadable(
            detail=f"`git {argv[0]}` exited {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout

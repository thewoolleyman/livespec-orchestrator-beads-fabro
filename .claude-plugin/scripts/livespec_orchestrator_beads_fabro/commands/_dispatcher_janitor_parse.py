"""Parsing helpers for `_dispatcher_janitor_checks`."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["Worktree", "lines", "parse_remote_heads", "parse_worktrees"]

_WORKTREE_LINE_PREFIX = "worktree "
_BRANCH_LINE_PREFIX = "branch refs/heads/"
_HEADS_REF_PREFIX = "refs/heads/"


@dataclass(frozen=True, kw_only=True, slots=True)
class Worktree:
    """One `git worktree list --porcelain` entry."""

    path: str
    branch: str | None
    is_primary: bool


def lines(*, raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def parse_remote_heads(*, raw: str | None) -> tuple[str, ...] | None:
    """Parse `git ls-remote --heads origin` output into branch names."""
    if raw is None:
        return None
    heads: list[str] = []
    for line in raw.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith(_HEADS_REF_PREFIX):
            heads.append(ref[len(_HEADS_REF_PREFIX) :].strip())
    return tuple(heads)


def parse_worktrees(*, raw: str | None) -> tuple[Worktree, ...] | None:
    """Parse `git worktree list --porcelain` blocks; the first entry is primary."""
    if raw is None:
        return None
    entries: list[Worktree] = []
    path: str | None = None
    branch: str | None = None
    for line in raw.splitlines():
        if line.startswith(_WORKTREE_LINE_PREFIX):
            if path is not None:
                entries.append(Worktree(path=path, branch=branch, is_primary=len(entries) == 0))
            path = line[len(_WORKTREE_LINE_PREFIX) :]
            branch = None
        elif line.startswith(_BRANCH_LINE_PREFIX):
            branch = line[len(_BRANCH_LINE_PREFIX) :]
    if path is not None:
        entries.append(Worktree(path=path, branch=branch, is_primary=len(entries) == 0))
    return tuple(entries)

"""Whole-tree survival decision for the sandbox clone (Scenario 197)."""

from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Callable, Sequence
from typing import Protocol

from livespec_shell_shape import (
    leading_assignments,
    shell_tokens,
    token_segments,
    without_heredoc_bodies,
)

_REMOVAL_VERBS = frozenset({"rm", "rmdir", "shred", "unlink"})
_MINIMUM_MOVE_OPERANDS = 2


class _Target(Protocol):
    path: str
    into_directory: bool


def repository_emptying_path(
    *,
    command: str,
    working_directory: str,
    clone: str,
    top_level_entries: Sequence[str],
    walk_segment: Callable[..., tuple[str, list[_Target]]],
    executed: Callable[..., tuple[str, list[str]]],
) -> str | None:
    """Return ``clone`` if executed removals and outward moves empty its visible top level."""
    normalized_clone = posixpath.normpath(clone)
    entries = tuple(
        entry
        for entry in (posixpath.normpath(path) for path in top_level_entries)
        if posixpath.dirname(entry) == normalized_clone
        and not posixpath.basename(entry).startswith(".")
    )
    if not entries:
        return None

    directory = working_directory
    assigned: dict[str, str] = {}
    removed: set[str] = set()
    for line in without_heredoc_bodies(command=command).splitlines():
        tokens = shell_tokens(command=line)
        if tokens is None:
            continue
        for segment in token_segments(tokens=tokens):
            assigned.update(leading_assignments(tokens=segment))
            verb, _ = executed(segment=segment)
            directory, targets = walk_segment(
                segment=segment, directory=directory, assigned=assigned
            )
            if verb in _REMOVAL_VERBS:
                removed.update(_covered_entries(targets=targets, entries=entries))
            elif (
                verb == "mv"
                and len(targets) >= _MINIMUM_MOVE_OPERANDS
                and not _inside(path=targets[-1].path, directory=normalized_clone)
            ):
                removed.update(_covered_entries(targets=targets[:-1], entries=entries))
    return normalized_clone if set(entries) <= removed else None


def _covered_entries(*, targets: Sequence[_Target], entries: Sequence[str]) -> set[str]:
    return {
        entry
        for target in targets
        if not target.into_directory
        for entry in entries
        if _matches_entry(target=target.path, entry=entry)
    }


def _matches_entry(*, target: str, entry: str) -> bool:
    return (
        fnmatch.fnmatchcase(entry, target)
        if any(character in target for character in "*?[")
        else entry == target or entry.startswith(f"{target}/")
    )


def _inside(*, path: str, directory: str) -> bool:
    return path == directory or path.startswith(f"{directory}/")

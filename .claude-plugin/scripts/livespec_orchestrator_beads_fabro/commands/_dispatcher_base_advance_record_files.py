"""Classify an overtaken pull request's read-only merge paths.

Scenario 184 permits its automatic-resume arm only for a non-empty conflict
set wholly declared by the target repository.  This leaf does not execute the
merge measurement or alter a repository; it decides whether the measured paths
are eligible once the Dispatcher has them.
"""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands import _jsonc

__all__: list[str] = ["record_file_resume_paths"]

_PLUGIN = "livespec-orchestrator-beads-fabro"
_DISPATCHER = "dispatcher"
_RECORD_FILES = "record_files"
_PATH = "path"


def record_file_resume_paths(
    *, config_text: str, conflicted_paths: tuple[str, ...]
) -> tuple[str, ...] | None:
    """Return an eligible non-empty path set, or ``None`` for every other case.

    A malformed declaration is deliberately not treated as a declaration of
    arbitrary paths.  The ordinary pre-dispatch configuration gate owns its
    operator-facing refusal; this post-run arm only admits a fact it can prove.
    """
    if not conflicted_paths:
        return None
    declared = _declared_paths(config_text=config_text)
    if declared is None or not declared or not all(path in declared for path in conflicted_paths):
        return None
    return conflicted_paths


def _declared_paths(*, config_text: str) -> frozenset[str] | None:
    """Read only a complete, unambiguous set of declared record-file paths."""
    entries = _record_entries(config_text=config_text)
    if entries is None:
        return None
    return _paths_from_entries(entries=entries)


def _record_entries(*, config_text: str) -> list[object] | None:
    """Read the raw declared entry list only when each containing object exists."""
    parsed = _jsonc.parse(text=config_text)
    if isinstance(parsed, _jsonc.JsoncFailure) or not isinstance(parsed, dict):
        return None
    plugin = cast("dict[str, object]", parsed).get(_PLUGIN)
    if not isinstance(plugin, dict):
        return None
    dispatcher = cast("dict[str, object]", plugin).get(_DISPATCHER)
    if not isinstance(dispatcher, dict):
        return None
    entries = cast("dict[str, object]", dispatcher).get(_RECORD_FILES)
    if not isinstance(entries, list):
        return None
    return cast("list[object]", entries)


def _paths_from_entries(*, entries: list[object]) -> frozenset[str] | None:
    """Read a complete, unambiguous path set from already-located entries."""
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        path = cast("dict[str, object]", entry).get(_PATH)
        if not isinstance(path, str) or not path or path in paths:
            return None
        paths.add(path)
    return frozenset(paths)

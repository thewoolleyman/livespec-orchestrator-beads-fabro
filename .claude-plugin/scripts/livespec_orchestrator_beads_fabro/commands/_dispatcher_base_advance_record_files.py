"""Classify an overtaken pull request's read-only merge paths.

Scenario 184 permits its automatic-resume arm only for a non-empty conflict
set wholly declared by the target repository.  This leaf does not execute the
merge measurement or alter a repository; it decides whether the measured paths
are eligible once the Dispatcher has them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc

__all__: list[str] = [
    "ConflictMeasurement",
    "measure_conflicted_paths",
    "record_file_resume_paths",
]

_PLUGIN = "livespec-orchestrator-beads-fabro"
_DISPATCHER = "dispatcher"
_RECORD_FILES = "record_files"
_PATH = "path"
_MERGE_TREE = ["git", "merge-tree", "--write-tree", "--name-only"]


class _CommandRunner(Protocol):
    """The Dispatcher command seam used for the read-only Git measurement."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> object:
        """Run one command through the Dispatcher's authenticated process seam."""


@dataclass(frozen=True, kw_only=True)
class ConflictMeasurement:
    """Either the complete conflict set or the failed measurement's detail."""

    paths: tuple[str, ...] | None
    failure: str | None


def measure_conflicted_paths(
    *,
    repo: Path,
    runner: _CommandRunner,
    pr_head: str,
    default_branch_tip: str,
) -> ConflictMeasurement:
    """Measure the two heads' conflicts without changing a ref or working tree.

    `merge-tree --write-tree --name-only` writes an ephemeral Git object only;
    it does not update a ref or checkout. Git exits one when it found conflicts,
    so that status is the successful measurement arm, not a failure.
    """
    result = runner.run(
        argv=[*_MERGE_TREE, pr_head, default_branch_tip],
        cwd=repo,
        timeout_seconds=30.0,
    )
    exit_code = getattr(result, "exit_code", None)
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    if exit_code != 1 or not isinstance(stdout, str):
        detail = stderr.strip() if isinstance(stderr, str) else ""
        return ConflictMeasurement(
            paths=None,
            failure=detail or f"git merge-tree exited {exit_code}",
        )
    paths = tuple(path for path in stdout.splitlines() if path)
    if not paths:
        return ConflictMeasurement(paths=None, failure="git merge-tree named no conflicted paths")
    return ConflictMeasurement(paths=paths, failure=None)


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

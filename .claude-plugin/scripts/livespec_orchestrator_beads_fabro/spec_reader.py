"""Spec Reader adapter for livespec-orchestrator-beads-fabro.

Implements the four required capabilities defined in
livespec/SPECIFICATION/contracts.md §"Spec Reader required-capability
surface" and concretized for this plugin in SPECIFICATION/contracts.md
§"Spec Reader internal API".

This v001 implementation is a thin file pass-through: every read goes
straight to the filesystem; no caching, no section-level indexing, no
embedding-based retrieval. The required-capability surface is satisfied
by direct `Path.read_text()` calls plus a unified-diff body for the
version-diff capability.

Public functions (all keyword-only):

- `read_current_specification(*, spec_root)` — returns a SpecSnapshot of
  the live spec tree at <spec-root>/, excluding `proposed_changes/`.
- `read_specification_history(*, spec_root, version)` — returns a
  SpecSnapshot of the <spec-root>/history/vNNN/ tree at the requested
  integer version.
- `current_specification_version(*, spec_root)` — returns the latest
  integer N such that <spec-root>/history/vNNN/ exists.
- `diff_specification_versions(*, spec_root, version_a, version_b)` —
  returns a SpecDiff comparing two history versions, file-by-file.

The well-known spec file set is discovered by directory traversal rather
than hardcoded. The Spec Reader honors the `version-directories-complete`
exemption (a vNNN/ directory may carry a `PRUNED_HISTORY.json` marker
indicating it was pruned per /livespec:prune-history); pruned
versions are returned as SpecSnapshots whose `files` map carries only the
`PRUNED_HISTORY.json` content.
"""

import difflib
import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.errors import SpecVersionNotFoundError
from livespec_orchestrator_beads_fabro.types import FileDiff, SpecDiff, SpecSnapshot

_VERSION_DIR_PATTERN = re.compile(r"^v(\d+)$")


def read_current_specification(*, spec_root: Path) -> SpecSnapshot:
    """Return a SpecSnapshot of the live <spec-root>/ tree."""
    files = _read_spec_directory(directory=spec_root, exclude={"history", "proposed_changes"})
    version = current_specification_version(spec_root=spec_root)
    return SpecSnapshot(version=version, files=files)


def read_specification_history(*, spec_root: Path, version: int) -> SpecSnapshot:
    """Return a SpecSnapshot of <spec-root>/history/v{version:03d}/."""
    version_dir = _version_directory(spec_root=spec_root, version=version)
    if not version_dir.exists():
        raise SpecVersionNotFoundError(spec_root=spec_root, version=version)
    files = _read_spec_directory(directory=version_dir, exclude=set())
    return SpecSnapshot(version=version, files=files)


def current_specification_version(*, spec_root: Path) -> int:
    """Return the latest vNNN integer present under <spec-root>/history/."""
    history_dir = spec_root / "history"
    if not history_dir.exists():
        return 0
    versions: list[int] = []
    for child in history_dir.iterdir():
        if not child.is_dir():
            continue
        match = _VERSION_DIR_PATTERN.match(child.name)
        if match is not None:
            versions.append(int(match.group(1)))
    return max(versions) if versions else 0


def diff_specification_versions(*, spec_root: Path, version_a: int, version_b: int) -> SpecDiff:
    """Return a SpecDiff comparing two history versions."""
    snapshot_a = read_specification_history(spec_root=spec_root, version=version_a)
    snapshot_b = read_specification_history(spec_root=spec_root, version=version_b)
    all_paths = sorted(set(snapshot_a.files.keys()) | set(snapshot_b.files.keys()))
    per_file: dict[str, FileDiff] = {}
    for path in all_paths:
        content_a = snapshot_a.files.get(path, "")
        content_b = snapshot_b.files.get(path, "")
        if content_a == content_b:
            continue
        per_file[path] = _file_diff(path=path, content_a=content_a, content_b=content_b)
    return SpecDiff(version_a=version_a, version_b=version_b, per_file=per_file)


def _read_spec_directory(*, directory: Path, exclude: set[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    for candidate in directory.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(directory)
        if any(part in exclude for part in relative.parts):
            continue
        files[str(relative)] = candidate.read_text(encoding="utf-8")
    return files


def _version_directory(*, spec_root: Path, version: int) -> Path:
    return spec_root / "history" / f"v{version:03d}"


def _file_diff(*, path: str, content_a: str, content_b: str) -> FileDiff:
    a_lines = content_a.splitlines(keepends=True)
    b_lines = content_b.splitlines(keepends=True)
    added = 0
    removed = 0
    for line in difflib.ndiff(a_lines, b_lines):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    unified = "".join(
        difflib.unified_diff(a_lines, b_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=3)
    )
    return FileDiff(path=path, added_lines=added, removed_lines=removed, unified_diff=unified)

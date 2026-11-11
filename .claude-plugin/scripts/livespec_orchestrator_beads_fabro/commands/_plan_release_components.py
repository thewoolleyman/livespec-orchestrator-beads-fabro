"""Committed release-component declarations and record artifact-path evidence."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    InvalidReleaseComponents,
    ReleaseComponent,
)

__all__: list[str] = ["artifact_paths_in", "release_components"]

_KEY = "dispatcher.release_components"
_COMPONENTS_KEY = "release_components"
_ARTIFACT_PATHS = re.compile(r"^\s*-\s+artifact paths:\s*(?P<paths>.+)$", re.IGNORECASE)


def artifact_paths_in(*, body: str) -> tuple[str, ...]:
    """The first artifact-paths line in a record, split in its written order."""
    for line in body.splitlines():
        matched = _ARTIFACT_PATHS.match(line)
        if matched is not None:
            return tuple(path.strip() for path in matched.group("paths").split(",") if path.strip())
    return ()


def release_components(
    *, project_root: Path, repository: str
) -> tuple[ReleaseComponent, ...] | InvalidReleaseComponents | None:
    """Read the governed repository's optional component declaration once."""
    block = dispatcher_block(cwd=project_root)
    if _COMPONENTS_KEY not in block:
        return None
    raw = cast("object", block[_COMPONENTS_KEY])
    if not isinstance(raw, list):
        return _invalid(repository=repository)
    components: list[ReleaseComponent] = []
    for entry in cast("list[object]", raw):
        parsed = _component(entry=entry)
        if parsed is None:
            return _invalid(repository=repository)
        components.append(parsed)
    return tuple(components)


def _component(*, entry: object) -> ReleaseComponent | None:
    if not isinstance(entry, dict):
        return None
    mapping = cast("dict[str, object]", entry)
    name = mapping.get("name")
    tag_prefix = mapping.get("tag_prefix")
    paths = mapping.get("paths")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(tag_prefix, str) or not tag_prefix.strip():
        return None
    if not isinstance(paths, list) or not paths:
        return None
    path_values = cast("list[object]", paths)
    if not all(_repository_relative(path=path) for path in path_values):
        return None
    typed_paths = tuple(cast("str", path) for path in path_values)
    return ReleaseComponent(name=name, tag_prefix=tag_prefix, paths=typed_paths)


def _repository_relative(*, path: object) -> bool:
    """A non-empty path prefix that stays inside the repository: not absolute, no parent segment."""
    if not isinstance(path, str) or not path.strip():
        return False
    pure = PurePosixPath(path.strip())
    return not pure.is_absolute() and ".." not in pure.parts


def _invalid(*, repository: str) -> InvalidReleaseComponents:
    return InvalidReleaseComponents(
        repository=repository,
        finding=(
            f"configuration finding: {_KEY} must be an array of named components"
            " with tag_prefix and non-empty paths"
        ),
    )

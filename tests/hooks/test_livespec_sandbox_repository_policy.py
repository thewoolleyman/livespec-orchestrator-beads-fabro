"""Unit coverage for the clone-top-level survival policy."""

from __future__ import annotations

import importlib.util
import posixpath
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_POLICY_PATH = _HOOKS_DIR / "livespec_sandbox_repository_policy.py"
_MODULE_NAME = "livespec_sandbox_repository_policy_under_test"
_CLONE = "/repos/example/repository"


@dataclass(frozen=True)
class _Target:
    path: str
    into_directory: bool = False


def _load_policy() -> ModuleType:
    assert _POLICY_PATH.is_file()
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _POLICY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _executed(*, segment: list[str]) -> tuple[str, list[str]]:
    return segment[0], []


def _walk_segment(
    *, segment: list[str], directory: str, assigned: dict[str, str]
) -> tuple[str, list[_Target]]:
    del assigned
    return directory, [
        _Target(
            path=(
                operand
                if operand.startswith("/")
                else posixpath.normpath(posixpath.join(directory, operand))
            )
        )
        for operand in segment[1:]
    ]


def _decision(*, command: str, entries: tuple[str, ...]) -> str | None:
    policy = _load_policy()
    return policy.repository_emptying_path(
        command=command,
        working_directory=_CLONE,
        clone=_CLONE,
        top_level_entries=entries,
        walk_segment=_walk_segment,
        executed=_executed,
    )


def test_removals_and_outward_moves_across_segments_emptying_the_clone_are_refused() -> None:
    entries = (f"{_CLONE}/build", f"{_CLONE}/src", f"{_CLONE}/README.md")

    assert (
        _decision(command="rm -rf build && mv src /tmp/src && rm README.md", entries=entries)
        == _CLONE
    )


def test_a_glob_of_visible_top_level_entries_names_the_clone() -> None:
    assert _decision(command="rm -rf ./*", entries=(f"{_CLONE}/src",)) == _CLONE


def test_a_move_whose_destination_is_inside_the_clone_does_not_count_as_removal() -> None:
    assert (
        _decision(
            command="mv build src",
            entries=(f"{_CLONE}/build", f"{_CLONE}/src"),
        )
        is None
    )

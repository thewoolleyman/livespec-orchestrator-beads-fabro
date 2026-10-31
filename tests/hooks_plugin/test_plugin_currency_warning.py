"""Scenario 271 coverage for registered-root prose bootstrapping."""

from __future__ import annotations

import re
import subprocess
import sys
from importlib.machinery import PathFinder
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"
_PROSE_DIR = _PLUGIN_ROOT / "prose"
_BOOTSTRAP_RE = re.compile(r"## Plugin Package Imports\n.*?```python\n(?P<code>.*?)```", re.DOTALL)


def _import_prose() -> list[Path]:
    return [
        path
        for path in sorted(_PROSE_DIR.glob("*.md"))
        if "livespec_orchestrator_beads_fabro" in path.read_text(encoding="utf-8")
    ]


def test_package_import_snippets_resolve_the_governed_projects_registered_root() -> None:
    """No operation prose import can inherit a stale literal cache-build path."""
    snippets = [path.read_text(encoding="utf-8") for path in _import_prose()]

    assert snippets
    for snippet in snippets:
        assert "registered_plugin_root.py" in snippet
        assert "_registered_plugin_root" in snippet
        assert 'sys.path.insert(0, f"{_registered_plugin_root}/scripts")' in snippet
        assert "/.claude/plugins/cache/" not in snippet


@pytest.mark.parametrize("prose", _import_prose(), ids=lambda path: path.stem)
def test_the_bootstrap_as_written_makes_the_package_and_its_vendored_runtime_importable(
    prose: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run each prose bootstrap verbatim; everything its imports need must resolve.

    The package imports `livespec_runtime`, which ships vendored under
    `scripts/_vendor`. A bootstrap that adds only `scripts` lets the first
    package import fail with ModuleNotFoundError, so this runs the snippet as
    written and resolves both names against the entries it added alone.
    """
    match = _BOOTSTRAP_RE.search(prose.read_text(encoding="utf-8"))
    assert match, f"{prose.name} has no Plugin Package Imports bootstrap"
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_PLUGIN_ROOT))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"{_PLUGIN_ROOT}\n", stderr=""
        ),
    )
    monkeypatch.setattr(sys, "path", list(sys.path))
    inherited = len(sys.path)

    exec(match.group("code"), {})  # noqa: S102 - the prose snippet is the subject

    # The bootstrap inserts at the front; resolve against those entries only,
    # since this test process already has the plugin's scripts on its path.
    added = sys.path[: len(sys.path) - inherited]
    for name in ("livespec_orchestrator_beads_fabro", "livespec_runtime"):
        assert (
            PathFinder.find_spec(name, added) is not None
        ), f"{prose.name}: {name} does not resolve from {added}"

"""Scenario 271 coverage for registered-root prose bootstrapping."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROSE_DIR = _REPO_ROOT / ".claude-plugin" / "prose"


def test_package_import_snippets_resolve_the_governed_projects_registered_root() -> None:
    """No operation prose import can inherit a stale literal cache-build path."""
    snippets = [
        path.read_text(encoding="utf-8")
        for path in sorted(_PROSE_DIR.glob("*.md"))
        if "livespec_orchestrator_beads_fabro" in path.read_text(encoding="utf-8")
    ]

    assert snippets
    for snippet in snippets:
        assert "registered_plugin_root.py" in snippet
        assert "_registered_plugin_root" in snippet
        assert 'sys.path.insert(0, f"{_registered_plugin_root}/scripts")' in snippet
        assert "/.claude/plugins/cache/" not in snippet

"""The Dispatcher resolves its Fabro workflow + bin from the PLUGIN ROOT.

Slice 1 of orchestrator-plugin-self-containment: `_workflow_toml` and
`_candidate_dispatcher_bin` must anchor on the plugin root (`.claude-plugin/`
in source, or `CLAUDE_PLUGIN_ROOT` in the flattened install cache) rather than
the repo root, and the `.fabro/` workflow payload must ship INSIDE that root.

Two properties under test:

1. With no `--workflow` override, `_workflow_toml` returns
   `<plugin-root>/.fabro/workflows/implement-work-item/workflow.toml`, where
   `<plugin-root>` is `Path(dispatcher.__file__).resolve().parents[3]` (the
   `.claude-plugin/` dir) — and that the packaged `workflow.toml` AND
   `workflow.fabro` actually exist there, so a future accidental drop of the
   payload fails CI (the structural guard for change (e)).
2. Both resolvers honor a non-empty `CLAUDE_PLUGIN_ROOT` env override (the
   cache-mode anchor) and otherwise fall back to the source `parents[3]` walk.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands.dispatcher import (
    _candidate_dispatcher_bin,  # pyright: ignore[reportPrivateUsage]
    _workflow_toml,  # pyright: ignore[reportPrivateUsage]
)

# The plugin root in source: `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/
# commands/dispatcher.py` → parents[3] is the `.claude-plugin/` dir.
_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_SUBPATH = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_PROMPTS_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item" / "prompts"


def test_workflow_toml_resolves_from_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default resolution anchors on the plugin root and the payload ships there."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    resolved = _workflow_toml(args=argparse.Namespace(workflow=None))
    assert resolved == _PLUGIN_ROOT.joinpath(*_WORKFLOW_SUBPATH)
    assert resolved.parts[-5:] == (
        ".claude-plugin",
        ".fabro",
        "workflows",
        "implement-work-item",
        "workflow.toml",
    )
    # Structural guard (e): the packaged workflow payload exists at the plugin
    # root — both the TOML manifest and its sibling Fabro phase graph — so an
    # accidental drop of the payload fails CI.
    assert resolved.is_file()
    assert (resolved.parent / "workflow.fabro").is_file()


def test_workflow_toml_honors_plugin_root_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-empty CLAUDE_PLUGIN_ROOT wins (the flattened install-cache anchor)."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    resolved = _workflow_toml(args=argparse.Namespace(workflow=None))
    assert resolved == tmp_path.joinpath(*_WORKFLOW_SUBPATH)


def test_workflow_override_arg_wins() -> None:
    """An explicit `--workflow <path>` still overrides the plugin-root default."""
    override = "/somewhere/else/workflow.toml"
    assert _workflow_toml(args=argparse.Namespace(workflow=override)) == Path(override)


def test_candidate_dispatcher_bin_resolves_from_plugin_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canary bin anchors on the same plugin root (no `.claude-plugin` re-segment)."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert _candidate_dispatcher_bin() == _PLUGIN_ROOT / "scripts" / "bin" / "dispatcher.py"


def test_candidate_dispatcher_bin_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The canary bin honors CLAUDE_PLUGIN_ROOT in the flattened install cache."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert _candidate_dispatcher_bin() == tmp_path / "scripts" / "bin" / "dispatcher.py"


def test_implement_and_review_prompts_enforce_scope_and_acceptance() -> None:
    """The shipped prompts carry the stage-consumption discipline."""
    implement_text = (_PROMPTS_DIR / "implement.md").read_text(encoding="utf-8")
    review_text = (_PROMPTS_DIR / "review.md").read_text(encoding="utf-8")

    assert "SCOPE-MINIMALISM" in implement_text
    assert "edit ONLY what the work-item requires" in implement_text
    assert "unrelated files, unrelated docs" in implement_text
    assert "acceptance criteria" in review_text
    assert "satisfies the work-item" in review_text
    assert "minimal scope" in review_text

"""Factory Driver-hook materialization is release-pinned before each agent turn."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_driver_hooks.py"
)


def test_prepare_steps_materialize_both_runtime_drivers_at_verified_releases() -> None:
    """Both adapters receive their Driver before the sandbox starts an agent turn."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks"
    )

    claude = module.claude_driver_hooks_prepare_steps_block()
    codex = module.codex_driver_hooks_prepare_steps_block()

    assert "livespec-driver-claude" in claude
    assert "hooks/pretooluse_dispatch.py" in claude
    assert '"ref": revision' in claude
    assert "refs/tags/v$version" in claude

    assert "livespec-driver-codex" in codex
    assert "livespec@livespec-driver-codex" in codex
    assert "require.resolve('@openai/codex/bin/codex.js'" in codex
    assert "verified_hook_keys" in codex
    assert "trusted_hash" in codex
    assert "trusted_content_hash" in codex
    assert "--dangerously-bypass-hook-trust" not in codex


def test_overlay_places_each_driver_materialization_before_its_consumer() -> None:
    """The Claude cache gate follows materialization; Codex trust follows its config."""
    overlay = (
        Path(__file__).parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_overlay.py"
    ).read_text(encoding="utf-8")

    assert "claude_driver_hooks_prepare_steps_block" in overlay
    assert "codex_driver_hooks_prepare_steps_block" in overlay
    assert overlay.index("claude_driver_hooks_prepare_steps_block") < overlay.index(
        "plugin_cache_gate_prepare_steps_block"
    )

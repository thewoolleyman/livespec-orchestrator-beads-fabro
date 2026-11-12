"""Codex-specific prepare-step assembly leaves the general overlay cohesive."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_overlay_codex.py"
)


def test_codex_prepare_steps_follow_the_codex_credential_projection() -> None:
    """Codex-only setup lands together and is absent without a Codex credential."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_codex"
    )

    assert module.codex_prepare_steps_block(codex_auth_snapshot=None, codex_otel_config=None) == ""
    rendered = module.codex_prepare_steps_block(
        codex_auth_snapshot='{"tokens": {}}', codex_otel_config="[otel]\n"
    )
    assert "auth.json" in rendered
    assert "config.toml" in rendered
    assert "livespec-driver-codex" in rendered

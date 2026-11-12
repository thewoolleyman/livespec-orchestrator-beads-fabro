"""The factory must materialize and trust the Codex Driver hook payload."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_codex_driver_hooks.py"
)


def test_prepare_materializer_installs_the_driver_and_trusts_release_verified_hooks() -> None:
    """The prepare script names the installed driver and its release-byte verifier."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_driver_hooks"
    )

    rendered = module.codex_driver_hooks_prepare_steps_block()

    assert "livespec-driver-codex" in rendered
    assert "livespec@livespec-driver-codex" in rendered
    assert "codex_hook_trust" in rendered
    assert "trusted_content_hash" in rendered
    assert "--dangerously-bypass-hook-trust" not in rendered


def test_prepare_materializer_resolves_codex_from_the_acp_package_dependency() -> None:
    """The ACP package's hoisted Codex dependency supplies the sandbox CLI."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_driver_hooks"
    )

    rendered = module.codex_driver_hooks_prepare_steps_block()

    assert "require.resolve('@openai/codex/bin/codex.js'" in rendered
    assert "@agentclientprotocol/codex-acp/node_modules/@openai/codex" not in rendered

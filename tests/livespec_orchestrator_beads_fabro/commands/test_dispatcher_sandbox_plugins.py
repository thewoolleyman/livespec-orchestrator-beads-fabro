"""The shared sandbox plugins-root expansion."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
    sandbox_plugins_root_expansion,
)


def test_the_root_has_one_override_and_one_production_default() -> None:
    assert SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR == "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"
    assert sandbox_plugins_root_expansion() == (
        "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}"
    )

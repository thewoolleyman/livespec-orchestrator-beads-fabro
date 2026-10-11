"""The one sandbox plugin-root expansion shared by materialized helpers."""

from __future__ import annotations

__all__: list[str] = [
    "SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR",
    "sandbox_plugins_root_expansion",
]

SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"


def sandbox_plugins_root_expansion() -> str:
    """The shell expansion every prepare and re-entry helper resolves."""
    return f"${{{SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR}:-$HOME/.claude/plugins}}"

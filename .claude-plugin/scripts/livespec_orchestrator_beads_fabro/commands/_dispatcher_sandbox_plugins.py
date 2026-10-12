"""The one sandbox plugin-root expansion shared by every materialized helper.

Written once, and PUBLIC, because a node resolving a DIFFERENT root than the
prepare pass that wrote the helper would find no helper at all -- and the
failure would then read as a Dispatcher that never materialized one, which
points at the wrong half of the seam.

THE ROOT IS RESOLVED BY SHELL EXPANSION RATHER THAN FROM A PROJECTED PATH, and
that is the established mechanism rather than a shortcut. The root is not known
host-side -- it is the sandbox's own `$HOME` unless the image overrides it --
and the pinned engine does not expand `${...}` inside an `[environments.*.env]`
value, so a projected path would reach the node as the literal dollar-brace
string.
"""

from __future__ import annotations

__all__: list[str] = [
    "SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR",
    "sandbox_plugins_root_expansion",
]

SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"


def sandbox_plugins_root_expansion() -> str:
    """The shell expansion every prepare step and re-entry helper resolves."""
    return f"${{{SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR}:-$HOME/.claude/plugins}}"

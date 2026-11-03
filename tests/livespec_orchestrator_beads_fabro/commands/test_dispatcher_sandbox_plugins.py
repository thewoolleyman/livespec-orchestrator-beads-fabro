"""The shared sandbox plugins-root expansion and its durable sandbox home.

Fabro restores ``/workspace`` when it reacquires a sandbox after a host error,
but it does not restore the container's original ``/root`` home. The Claude
Agent SDK and Dispatcher helpers both default their plugin state below
``$HOME/.claude/plugins``. The overlay must therefore make the sandbox home
the durable workspace before either prepare steps or nodes run.
"""

from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
    sandbox_plugins_root_expansion,
)

_COMMITTED = '[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n'


def test_the_root_has_one_override_and_one_production_default() -> None:
    assert SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR == "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"
    assert sandbox_plugins_root_expansion() == (
        "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}"
    )


def test_the_dispatcher_places_the_default_plugin_root_in_the_durable_workspace(
    tmp_path: Path,
) -> None:
    """A resumed sandbox resolves its SDK cache and helpers below `/workspace`."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token="",
        github_token="",
        siblings=None,
    )

    assert rendered is not None
    overlay = tomli.loads(rendered)
    environment = overlay["environments"]["sandbox"]["env"]
    assert environment.get("HOME") == "/workspace"

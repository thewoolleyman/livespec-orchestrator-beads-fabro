"""The settings file that makes the harness shell-tool policy the EFFECTIVE one.

The Dispatcher already projects the policy into the sandbox PROCESS environment
(`_dispatcher_overlay.harness_shell_env_lines`), and it arrives. It is then
overridden: the sandbox agent is the Claude harness, which loads the governed
repository's committed `.claude/settings.json` as its `project` settings source,
and a settings-file `env` value outranks the same variable inherited from the
process environment. This repository's committed file caps `BASH_MAX_TIMEOUT_MS`
at 1200000 ms for its interactive host sessions, so every sandbox shell call was
ended at ~1202 s while the overlay said 3600000.

Measured on the operator host with a 50-second foreground call requesting a
90000 ms timeout against an inherited 120000: project settings of 30000 ended it
at 30 s, no settings file let it run the full 50 s, and a `settings.local.json`
of 120000 beside project settings of 30000 ALSO let it run the full 50 s. So the
`local` source outranks the `project` source, and writing one is the only route
that leaves the committed file — the interactive sessions' setting — alone.

WHY THE RENDERER TAKES THE MAPPING RATHER THAN OWNING IT. The env table and this
file have to say the SAME thing: a sandbox whose settings file disagreed with its
own environment would be the identical fault one layer down, and it would be
invisible, because both layers would be individually well-formed. The overlay
therefore hands this renderer the very tuple it renders the table from, which is
what the third assertion below measures.
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path
from typing import Any

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_harness_settings"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_SETTINGS_PATH = "/workspace/.claude/settings.local.json"
_HARNESS_ENV = (
    ("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1"),
    ("BASH_DEFAULT_TIMEOUT_MS", "600000"),
    ("BASH_MAX_TIMEOUT_MS", "3600000"),
)


def _settings_module() -> Any:
    """The renderer module, through an in-body import.

    In-body rather than at module top so this file's FIRST failing assertion is
    a genuine check on the committed file rather than a collection error.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _rendered_env(*, script: str) -> dict[str, str]:
    """The env mapping the rendered step's own command line carries.

    Read by TOKENIZING the script the way a shell does and decoding its last
    argument, rather than by matching the mapping's rendered text. A substring
    match would pass on a payload sitting anywhere in the block — including one
    quoted into a comment — and this has to establish that the writer program is
    actually HANDED those keys.
    """
    argv = shlex.split(script)
    decoded: dict[str, str] = json.loads(argv[-1])
    return decoded


def test_the_prepare_step_writes_the_harness_env_into_the_sandbox_settings_file() -> None:
    """One step, naming the local settings path, carrying the mapping verbatim."""
    module = _settings_module()
    assert "harness_settings_prepare_steps_block" in module.__all__
    rendered: str = module.harness_settings_prepare_steps_block(harness_env=_HARNESS_ENV)
    assert rendered.count("[[run.prepare.steps]]") == 1
    import tomli

    block: dict[str, Any] = tomli.loads(rendered)
    steps: list[dict[str, str]] = block["run"]["prepare"]["steps"]
    script = steps[0]["script"]
    assert _SETTINGS_PATH in script
    assert _rendered_env(script=script) == dict(_HARNESS_ENV)

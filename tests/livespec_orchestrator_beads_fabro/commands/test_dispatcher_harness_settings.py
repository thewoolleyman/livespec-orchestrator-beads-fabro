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

WHERE THE FILE HAS TO LAND, which is the assertion this file gained after the
first implementation wrote a file nothing read. The harness resolves BOTH of its
file-based sources against ITS OWN working directory and walks no parent, so the
`local` file is only read when it sits beside the committed `project` file — and
that directory is the sandbox CLONE, not `/workspace`. Measured inside an hp
sandbox on 2026-10-15: `/workspace` is not a repository at all and holds no
`.claude/settings.json`, while the clone's own committed file supplied the
effective 1200000 ms cap. So the path is asserted as the RESOLVED CHECKOUT ROOT
joined with the relative path, and the absolute `/workspace` spelling is asserted
ABSENT — a renderer that reverts to it fails here rather than silently writing an
inert file again.
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

# Spelled as literals and bound to the module's exported names by the assertions
# below, because this file's Red predates the constant it binds and a Red's test
# bytes are fixed across its Red-to-Green pair.
_RELATIVE_SETTINGS_PATH = ".claude/settings.local.json"
_CHECKOUT_ROOT_PROBE = "git rev-parse --show-toplevel"
_INERT_ABSOLUTE_PATH = "/workspace/.claude/settings.local.json"
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


def _rendered_script(*, module: Any) -> str:
    """The single prepare step the renderer emits, read back through TOML.

    Parsed rather than substring-matched because the block's own comment names
    the settings path too, and the count of STEPS is what tells one projection
    apart from a duplicated one.

    `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the stdlib
    module does not exist yet.
    """
    rendered: str = module.harness_settings_prepare_steps_block(harness_env=_HARNESS_ENV)
    assert rendered.count("[[run.prepare.steps]]") == 1
    import tomli

    block: dict[str, Any] = tomli.loads(rendered)
    steps: list[dict[str, str]] = block["run"]["prepare"]["steps"]
    assert len(steps) == 1, steps
    return steps[0]["script"]


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
    script = _rendered_script(module=module)
    assert _RELATIVE_SETTINGS_PATH in script
    assert _rendered_env(script=script) == dict(_HARNESS_ENV)


def test_the_settings_file_is_written_inside_the_run_s_own_checkout() -> None:
    """The path argument is the RESOLVED checkout root joined with the suffix.

    This is the assertion that separates a settings file the harness loads from
    one it never looks at. The two file-based sources are siblings under the
    harness's own working directory — the clone — so a step that writes an
    absolute `/workspace` path produces a well-formed file, exits 0, and leaves
    the committed cap in force. Both halves are asserted: the step PROBES for the
    checkout root, and the path it hands the writer is derived from that probe's
    answer rather than spelled absolutely.
    """
    module = _settings_module()
    script = _rendered_script(module=module)
    assert _INERT_ABSOLUTE_PATH not in script
    assert _CHECKOUT_ROOT_PROBE in script
    # The second-to-last token is the writer's path argument; the last is the
    # env payload `_rendered_env` decodes.
    path_argument = shlex.split(script)[-2]
    assert path_argument.endswith(f"/{_RELATIVE_SETTINGS_PATH}")
    assert not path_argument.startswith("/"), path_argument
    assert module.SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH == _RELATIVE_SETTINGS_PATH
    assert "SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH" in module.__all__

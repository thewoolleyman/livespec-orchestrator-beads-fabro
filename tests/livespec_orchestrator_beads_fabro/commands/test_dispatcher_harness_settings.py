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

THE PATH IS RESOLVED IN THE SANDBOX, AND THAT IS WHAT THE FIRST TWO ASSERTIONS
BIND. A `local` source is only loaded from the directory the `project` source was
loaded from, and the two engines put the clone in DIFFERENT places inside the
workspace mount: the pinned engine checks it out at `/workspace/<repo>` and the
Petri-era engine AT `/workspace`. Measured in an hp review sandbox on
2026-10-15, the agent's cwd was `/repos/<owner>/<repo>`, `/workspace/.claude` did
not exist, and no ancestor of the clone carried a `.claude` at all — so a
workspace-rooted settings file is loaded by no settings source on that layout,
and the projection was a no-op for the very defect it exists to close. The clone
root is therefore resolved in-sandbox with `git rev-parse --show-toplevel`, the
same measurement `_dispatcher_sandbox_worktree_exclude` takes for the same
hazard.

AND THE FILE HAS TO BE HIDDEN FROM THE RUN'S OWN WORKTREE. On the Petri-era
layout the clone IS `/workspace`, so a clone-relative settings file sits inside
the run's worktree and the per-step checkpoint commits it into the run branch and
the draft pull request — the defect `bd-ib-dud2ww` and `bd-ib-ccywva` each hit
with their own materialized path. The exclusion is asserted BY IDENTITY against
the shared renderer rather than by matching its text, because the shared renderer
is what `_dispatcher_sandbox_worktree_exclude` requires of every projection that
materializes a path; a local re-implementation would satisfy a text match while
re-opening exactly what the sharing exists to prevent.

WHY THE RENDERER TAKES THE MAPPING RATHER THAN OWNING IT. The env table and this
file have to say the SAME thing: a sandbox whose settings file disagreed with its
own environment would be the identical fault one layer down, and it would be
invisible, because both layers would be individually well-formed. The overlay
therefore hands this renderer the very tuple it renders the table from, which is
what the last assertion below measures.
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_harness_settings"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

# Spelled as LITERALS here and bound to the module's own names by the first
# assertion: this file's Red predates the constants it binds, and a Red's test
# bytes are fixed across its Red-to-Green pair.
_RELATIVE_PATH = ".claude/settings.local.json"
_CLONE_ROOT_EXPANSION = "$(git rev-parse --show-toplevel)"
_EXCLUDE_PATH = f"{_CLONE_ROOT_EXPANSION}/{_RELATIVE_PATH}"
_EXCLUDE_LABEL = "livespec-harness-settings"
# The inert path this projection used to name, asserted ABSENT: it is a settings
# source on at most one engine's layout and is none on the layout hp runs.
_WORKSPACE_ROOTED_PATH = "/workspace/.claude/settings.local.json"
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


def _rendered_scripts(*, rendered: str) -> list[str]:
    """Every prepare-step script the rendered block carries, in order.

    Read by PARSING the block rather than by matching its text: the block's own
    comment names the settings path too, so a substring count would report a step
    that is not there — and the ORDER is load-bearing, since a file written
    before its exclusion is in place is a file the step's own checkpoint commits.

    `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the stdlib
    module does not exist yet.
    """
    import tomli

    block: dict[str, Any] = tomli.loads(rendered)
    steps: list[dict[str, str]] = block["run"]["prepare"]["steps"]
    return [step["script"] for step in steps]


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


def test_the_settings_path_is_resolved_from_the_sandbox_clone_root() -> None:
    """The clone-relative tail is named once, and no workspace-rooted path is."""
    module = _settings_module()
    assert "SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH" in module.__all__
    assert getattr(module, "SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH", None) == _RELATIVE_PATH
    rendered: str = module.harness_settings_prepare_steps_block(harness_env=_HARNESS_ENV)
    assert _WORKSPACE_ROOTED_PATH not in rendered
    assert _CLONE_ROOT_EXPANSION in rendered


def test_the_block_hides_the_settings_file_through_the_shared_exclude_renderer() -> None:
    """Step one is the shared exclusion, for the same path, rendered FIRST."""
    module = _settings_module()
    rendered: str = module.harness_settings_prepare_steps_block(harness_env=_HARNESS_ENV)
    scripts = _rendered_scripts(rendered=rendered)
    assert len(scripts) == 2, scripts
    assert scripts[0] == worktree_exclude_script(
        paths=(_EXCLUDE_PATH,),
        label=_EXCLUDE_LABEL,
    )


def test_the_prepare_step_writes_the_harness_env_into_the_sandbox_settings_file() -> None:
    """The writer names the clone-resolved local path and carries the mapping."""
    module = _settings_module()
    assert "harness_settings_prepare_steps_block" in module.__all__
    rendered: str = module.harness_settings_prepare_steps_block(harness_env=_HARNESS_ENV)
    write = _rendered_scripts(rendered=rendered)[-1]
    assert f'"$toplevel/{_RELATIVE_PATH}"' in write
    assert _rendered_env(script=write) == dict(_HARNESS_ENV)

"""The sandbox settings file that makes the harness shell-tool policy EFFECTIVE.

`_dispatcher_overlay` already projects that policy into the sandbox PROCESS
environment, and it arrives: hp run 01M4XWYERJEZ15GNMGHV66CSBY records
`BASH_MAX_TIMEOUT_MS=3600000` in its own `run.created` environment. It is then
OVERRIDDEN one layer down. The sandbox agent is `claude-agent-acp`, which starts
the Claude harness with `settingSources: ["user", "project", "local"]`, so the
governed repository's committed `.claude/settings.json` — carried into the
sandbox by the clone itself — is loaded as the `project` source; and a
settings-file `env` value outranks the same variable inherited from the process
environment. This repository's committed file caps `BASH_MAX_TIMEOUT_MS` at
1200000 ms, so that is the cap every sandbox shell call actually got. Two runs
lost their Green amend to it at 1202 s (`bd-ib-rv2jk4`).

WHY `settings.local.json` AND NOT THE COMMITTED FILE. Precedence was measured on
the operator host with a 50-second foreground call requesting a 90000 ms timeout
against an inherited 120000: project settings of 30000 ended it at 30 s, no
settings file let it run the full 50 s, and a `settings.local.json` of 120000
beside project settings of 30000 ALSO let it run the full 50 s. The `local`
source therefore outranks the `project` source, which is the only route that
raises the sandbox's cap while leaving the committed file — the INTERACTIVE host
sessions' setting, which this change deliberately does not touch — alone. That
path is already `.gitignore`-d here, so the file the step writes is invisible to
the agent's own commits and to the engine's checkpoint commit.

WHY THE MAPPING IS AN ARGUMENT RATHER THAN A CONSTANT HERE. The env table and
this file have to say the SAME thing: a settings file disagreeing with its own
process environment would be the identical fault one layer down, and it would be
invisible, because both layers would be individually well-formed. The overlay
hands this renderer the very tuple it renders the table from, so the two cannot
drift.

THIS RAISES NO CAP. It makes the overlay's EXISTING value the effective one.
Hook runtime depends on host load, so no fixed cap is the fix for a commit hook
that outlasts the tool-call limit.
"""

from __future__ import annotations

import json
import shlex

__all__: list[str] = [
    "SANDBOX_SETTINGS_LOCAL_PATH",
    "harness_settings_prepare_steps_block",
]

# The `local` settings source, at the sandbox clone's root. The pinned engine
# and the Petri-era engine disagree about where the clone sits, and this is the
# path that is right for the layout the measurement was taken on: the committed
# `.claude/settings.json` this file has to outrank arrives at
# `/workspace/.claude/settings.json`, so its `local` sibling is beside it.
SANDBOX_SETTINGS_LOCAL_PATH = "/workspace/.claude/settings.local.json"

# The writer, run as `python3 -c '<this>'` with the settings path and the env
# JSON as argv. It MERGES rather than replaces: a settings file the sandbox
# already carries may hold permissions, hooks or plugin declarations that are
# none of this projection's business, so only the `env` keys this dispatch
# names are written and every other key of the file survives. The keys we name
# WIN over any same-named key already in that `env` object, which is the whole
# point of writing it.
#
# Every string literal inside is DOUBLE-quoted, because the program is handed to
# the shell inside a single-quoted literal and one apostrophe would end it early.
# `python3` rather than a coreutils pipeline for the reason
# `_dispatcher_publication_metadata` gives: the prepare chain already depends on
# it hard, since the plugin-cache gate executes under it.
_SETTINGS_WRITER_PROGRAM = (
    "import json, pathlib, sys; "
    "path = pathlib.Path(sys.argv[1]); "
    'existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}; '
    'env = dict(existing.get("env") or {}); '
    "env.update(json.loads(sys.argv[2])); "
    'existing["env"] = env; '
    "path.parent.mkdir(parents=True, exist_ok=True); "
    'path.write_text(json.dumps(existing, indent=2) + chr(10), encoding="utf-8")'
)


def harness_settings_prepare_steps_block(*, harness_env: tuple[tuple[str, str], ...]) -> str:
    """Render the settings-file `[[run.prepare.steps]]` block.

    The mapping is `shlex.quote`-ed rather than interpolated raw: it reaches the
    writer as one shell word, and a value carrying a quote would otherwise end
    its literal and turn an env entry into a command. The whole script is then
    `json.dumps`-ed to TOML-quote it, matching every sibling block in the
    overlay — a value written raw there is a parse hazard that fails not this
    dispatch but EVERY dispatch through the run config.
    """
    payload = shlex.quote(json.dumps(dict(harness_env)))
    script = (
        "set -eu\n"
        f"python3 -c '{_SETTINGS_WRITER_PROGRAM}' '{SANDBOX_SETTINGS_LOCAL_PATH}' {payload}"
    )
    return (
        "\n# --- Dispatcher-materialized harness shell-tool policy: the `local`\n"
        "# --- settings source, which outranks the governed repository's committed\n"
        "# --- `.claude/settings.json` and therefore decides the sandbox agent's\n"
        "# --- effective shell tool-call cap (bd-ib-rv2jk4) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )

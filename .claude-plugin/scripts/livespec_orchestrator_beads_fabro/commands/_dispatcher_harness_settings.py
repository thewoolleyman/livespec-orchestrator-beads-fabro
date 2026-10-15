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

WHERE THE FILE GOES, which the first implementation of this module got wrong in
the one way that leaves every layer well-formed. The harness resolves BOTH of its
file-based sources against ITS OWN WORKING DIRECTORY and walks no parent: the
agent SDK's resolver takes `resolve(cwd)` as the base for the `project` and
`local` sources alike and joins `.claude/settings.json` /
`.claude/settings.local.json` onto it, so the two are always SIBLINGS under one
directory. That directory is the sandbox CLONE. Measured inside an hp sandbox on
2026-10-15: `/workspace` is not a repository at all (`git -C /workspace rev-parse
--show-toplevel` answers "not a git repository") and holds no
`.claude/settings.json`, the clone is reached through the symlink
`/workspace/<repo>`, and the effective cap was the committed 1200000 ms — which
only the CLONE's own `project` source can have supplied. An absolute
`/workspace/.claude/settings.local.json` is therefore a file the harness never
opens: the step exits 0, the file is valid JSON, the mapping inside it is exactly
right, and the cap it was written to raise stays where it was.

So the path is RESOLVED at prepare time from the run's own checkout root rather
than spelled absolutely, and an unresolvable root FAILS THE STEP rather than
writing somewhere plausible. That direction is the one the sibling
dispatch-base fetch argues for and it holds here for the same reason: without the
effective cap a run spends its whole implement stage and then loses the turn at
~1202 s, so a root that could not be resolved is cheaper to report in preparation
than to discover at the end of a full run. The sibling `git config` step of the
credential-helper projection already dies on exactly this condition, so the
prepare chain carries no weaker expectation than this step does.

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
    "SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH",
    "harness_settings_prepare_steps_block",
]

# The `local` settings source, RELATIVE to the run's own checkout root — the
# directory the harness resolves its settings sources against, and the one the
# committed `project` file this must outrank arrives in. It is a suffix rather
# than an absolute path for the docstring's reason: the two engines disagree
# about where the clone sits (`/workspace/<repo>` on the pinned engine,
# `/workspace` on the Petri-era one), so any absolute spelling is right for at
# most one of them and inert on the other.
SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH = ".claude/settings.local.json"

# The label every diagnostic this step can emit carries, so a line in a run's
# prepare output is attributable to this projection rather than to one of the
# several siblings that also shell out to git.
_DIAGNOSTIC_LABEL = "livespec-harness-settings"

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

    The destination is resolved by ASKING GIT for the worktree top rather than by
    trusting the step's working directory, so one spelling covers both sandbox
    layouts and the answer is the physical path git itself reports — the
    normalization `_dispatcher_sandbox_worktree_exclude` records as load-bearing,
    since a configured root reaches this sandbox family as a symlink.
    """
    payload = shlex.quote(json.dumps(dict(harness_env)))
    script = (
        "set -eu\n"
        'checkout_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"\n'
        'if [ -z "$checkout_root" ]; then\n'
        f'  echo "{_DIAGNOSTIC_LABEL}: no git worktree top resolved from'
        " '$PWD', so the harness local settings source cannot be written beside"
        " the committed project one that outranks this dispatch's environment;"
        ' failing closed rather than driving an implement stage under that cap" >&2\n'
        "  exit 1\n"
        "fi\n"
        f"python3 -c '{_SETTINGS_WRITER_PROGRAM}'"
        f' "$checkout_root/{SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH}" {payload}'
    )
    return (
        "\n# --- Dispatcher-materialized harness shell-tool policy: the `local`\n"
        "# --- settings source, written beside the governed repository's committed\n"
        "# --- `.claude/settings.json` in the run's own checkout, which it outranks\n"
        "# --- and so decides the sandbox agent's effective shell tool-call cap\n"
        "# --- (bd-ib-rv2jk4) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )

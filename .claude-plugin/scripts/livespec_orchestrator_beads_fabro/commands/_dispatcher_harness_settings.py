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

WHY THE CLONE ROOT IS RESOLVED IN THE SANDBOX RATHER THAN SPELLED HERE. A
`local` source is loaded from the directory its `project` sibling was loaded
from, which is the clone — and the two engines put the clone in DIFFERENT places
inside the workspace mount: the pinned engine checks it out at
`/workspace/<repo>` and the Petri-era engine AT `/workspace`
(`_dispatcher_sibling_clones` and `_dispatcher_sandbox_worktree_exclude` both
record the split). So no host-side literal is right on both, and the layout hp
runs is right for neither: measured in an hp sandbox on 2026-10-15, the agent's
cwd was `/repos/<owner>/<repo>`, `/workspace/.claude` did not exist, and no
ancestor of the clone carried a `.claude` at all. A `/workspace`-rooted file was
therefore loaded by NO settings source, which made this projection a silent
no-op for the one defect it exists to close. `git rev-parse --show-toplevel`
answers the question in the sandbox instead — the same measurement the exclude
renderer takes for the same hazard — and its command is spelled ONCE here,
because the exclusion and the writer must name one file and a second spelling is
how an exclusion comes to hide a path nothing writes.

WHY THE FILE IS HIDDEN FROM THE RUN'S OWN WORKTREE. A clone-relative path is
INSIDE the run's worktree on every engine, and the Petri-era engine runs each
prepare step as a graph node and checkpoints after it — so the step that writes
this file is a step whose checkpoint commits it into the run branch and the draft
pull request, as a change no implementer wrote. That is the defect `bd-ib-dud2ww`
and `bd-ib-ccywva` each hit with their own materialized path, so the exclusion
goes through the ONE shared renderer rather than being re-derived here, and it is
rendered FIRST for the checkpoint reason both of those callers give. This
repository's own `.gitignore` happens to cover the path, but the exclude module's
contract is that a GOVERNED repository must not have to carry a rule about a
Dispatcher-materialized path, and this plugin dispatches repositories that do
not.

WHY THE MAPPING IS AN ARGUMENT RATHER THAN A CONSTANT HERE. The env table and
this file have to say the SAME thing: a settings file disagreeing with its own
process environment would be the identical fault one layer down, and it would be
invisible, because both layers would be individually well-formed. The overlay
hands this renderer the very tuple it renders the table from, so the two cannot
drift. That tuple is a SUPERSET of the two ceilings: it also carries
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, so this file promotes that harness policy
key into a settings source outranking the governed repository's own committed
project file too. That follows from rendering both layers from one tuple, and the
no-drift guarantee is worth it; an adopter who must override that key does so in
their `user` settings or by changing the table.

THIS RAISES NO CAP. It makes the overlay's EXISTING value the effective one.
Hook runtime depends on host load, so no fixed cap is the fix for a commit hook
that outlasts the tool-call limit.
"""

from __future__ import annotations

import json
import shlex

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)

__all__: list[str] = [
    "SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH",
    "harness_settings_prepare_steps_block",
]

# How the sandbox clone's root is measured, spelled ONCE for both steps — see the
# module docstring. The prepare step runs inside the clone, so this needs no
# `-C`: the committed unshallow and `_dispatcher_default_branch_fetch`'s own
# bare `git fetch` already depend on exactly that.
_CLONE_ROOT_COMMAND = "git rev-parse --show-toplevel"

# The `local` settings source, as its path RELATIVE to that root. Public so the
# overlay's own tests can bind one spelling of it rather than re-deriving the
# tail a second time.
SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH = ".claude/settings.local.json"

# The same path as ONE shell word, for the exclusion. `worktree_exclude_script`
# hands each path to the sandbox's own shell inside a double-quoted `set --`
# word, so the substitution is resolved there, by the step, exactly as the
# writer's own assignment resolves it — which is what makes the excluded path and
# the written path the same file on every layout.
_SANDBOX_SETTINGS_EXCLUDE_PATH = f"$({_CLONE_ROOT_COMMAND})/{SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH}"

# Prefixes every diagnostic the exclusion can emit. Required by that renderer
# rather than defaulted, so a passed-over path names THIS projection.
_EXCLUDE_LABEL = "livespec-harness-settings"

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

    Two steps: the shared worktree exclusion, then the writer. The order is the
    same one `_dispatcher_gh_refresh` and `_dispatcher_credential_use_projection`
    render, and for the same reason — a file written before its exclusion is in
    place is a file the writing step's own checkpoint commits.

    The writer resolves the clone root into a VARIABLE under `set -e` rather than
    substituting it straight into the command line: an assignment whose command
    substitution fails takes that failure as its own status, so an unresolvable
    clone root kills the step instead of writing a settings file at `/.claude`
    that the harness would never load. A failing prepare step kills the run at
    launch, before any work is driven, which is the direction this has to fail in
    — the defect being closed is a projection that silently did nothing.

    The mapping is `shlex.quote`-ed rather than interpolated raw: it reaches the
    writer as one shell word, and a value carrying a quote would otherwise end
    its literal and turn an env entry into a command. Each script is then
    `json.dumps`-ed to TOML-quote it, matching every sibling block in the
    overlay — a value written raw there is a parse hazard that fails not this
    dispatch but EVERY dispatch through the run config.
    """
    payload = shlex.quote(json.dumps(dict(harness_env)))
    exclude = worktree_exclude_script(
        paths=(_SANDBOX_SETTINGS_EXCLUDE_PATH,),
        label=_EXCLUDE_LABEL,
    )
    write = (
        "set -eu\n"
        f'toplevel="$({_CLONE_ROOT_COMMAND})"\n'
        f"python3 -c '{_SETTINGS_WRITER_PROGRAM}'"
        f' "$toplevel/{SANDBOX_SETTINGS_LOCAL_RELATIVE_PATH}" {payload}'
    )
    lines = [
        "",
        "# --- Dispatcher-materialized harness shell-tool policy: hide the file",
        "# --- from the run's own worktree, then write the `local` settings",
        "# --- source, which outranks the governed repository's committed",
        "# --- `.claude/settings.json` and therefore decides the sandbox agent's",
        "# --- effective shell tool-call cap (bd-ib-rv2jk4) ---",
    ]
    for script in (exclude, write):
        lines.extend(["[[run.prepare.steps]]", f"script = {json.dumps(script)}"])
    return "\n".join(lines) + "\n"

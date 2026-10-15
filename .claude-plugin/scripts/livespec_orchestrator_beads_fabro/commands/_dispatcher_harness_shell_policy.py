"""The Claude harness's own shell-tool policy, as the TWO projections it needs.

Split out of `_dispatcher_overlay` by cohesion once the policy stopped being one
env table: that file ASSEMBLES the overlay, while this -- like
`_dispatcher_tmux_socket_root` and every other Dispatcher-materialized
projection -- is ONE policy, carrying the keys, the `[environments.<id>.env]`
lines that put them in the sandbox PROCESS environment, and the prepare steps
that put the SAME keys in the sandbox's own `local` settings file. Keeping the
three together is the point, and it is the whole repair below: a dispatch that
declared one ceiling in the environment and another in a settings file would
have no way to say which the harness obeyed, and splitting them across modules
is how two of them come to name different values.

WHY A FILE, when the env table already projects the same keys into the sandbox
PROCESS environment and they demonstrably arrive. The sandbox agent is
`@agentclientprotocol/claude-agent-acp`, which starts the Claude harness with
`settingSources: ["user", "project", "local"]`, so the governed repository's own
committed `.claude/settings.json` is loaded INSIDE the sandbox -- and a
settings-file `env` value OVERRIDES the same variable inherited from the process
environment. This fleet's committed project file carries the 1200000 ms ceiling
an interactive host session wants, so that file, not the overlay, decided the cap
for every factory dispatch. Measured on run 01M4XWYERJEZ15GNMGHV66CSBY, whose
`run.created` environment carries `BASH_MAX_TIMEOUT_MS=3600000` and whose two
final Green amends were ended at 1202366 ms and 1203117 ms; run
01M4TZQKSKWFWAZZ3QX6ZM3D8N lost its Green amend at 1202 s the same way
(work-item bd-ib-rv2jk4).

WHY THE `local` SOURCE AND NOT THE COMMITTED `project` ONE. The ranking was
measured on the operator host with a 50-second call requesting a 90000 ms
timeout: project settings at 30000 ended it, no settings file at all let it
complete, and the same project settings BESIDE a `.claude/settings.local.json`
at 120000 let it complete -- so `local` outranks `project`. Writing the local
file is therefore what makes the overlay's declaration effective, and it leaves
the committed project file alone, which is right for a second reason: that file
is the interactive host sessions' setting and is not the factory's to rewrite.

THIS RAISES NO CEILING. It makes the ceiling the env table already declares the
EFFECTIVE one. Both projections render from the ONE `_HARNESS_SHELL_ENV` tuple
below, because the whole defect is two sources of truth for one cap disagreeing:
a second spelling inside the fix would be the same fault one layer along.

THE WRITE MERGES rather than replacing. A sandbox that already carries a
`settings.local.json` keeps every other key it holds -- hooks, permissions,
anything a prepare step or an image put there -- and only the `env` members this
projection names are replaced. A file holding no JSON object cannot be merged
into, so that one arm writes a fresh document and SAYS SO on stderr: the
alternative is a prepare-step failure, which kills the run at launch before any
work is driven, over a per-sandbox file that no longer parses.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)

__all__: list[str] = [
    "HARNESS_SETTINGS_MARKER",
    "SANDBOX_HARNESS_SETTINGS_PATH",
    "harness_settings_merge_program",
    "harness_settings_prepare_steps_block",
    "harness_shell_env_lines",
]

# The Claude harness's own shell-tool policy, projected as NON-SECRET
# configuration beside the tmux socket root `_dispatcher_tmux_socket_root`
# projects.
#
# The harness moves a foreground shell call that REACHES its timeout into a
# background task; the ACP engine then raises `BackgroundedTool` and ENDS the
# turn. So an honest long foreground call — a full pytest run, a coverage pass —
# destroys the stage instead of returning late, and nothing on the agent's side
# can prevent it: the decision is the harness's, taken after the call has
# already run out its clock. Setting this switch makes such a call report back
# as an ordinary timed-out call the agent can read and retry
# (work-item bd-ib-k627ja; plan `pr-stage-backgrounded-push-fault`).
#
# The two timeouts are the OTHER half of the same fault and are not merely a
# convenience beside it. The harness defaults a foreground call to 120000 ms and
# CAPS a model-supplied timeout at 600000 ms, so a call that honestly needs
# twenty minutes — a full pytest run, a coverage pass — cannot ask for the time
# it needs however carefully the agent reasons about it. Raising the default to
# the old cap and the cap to an hour lets the call declare its real duration;
# the switch above then makes the remaining overruns survivable rather than
# turn-ending. Three P4 implement runs were destroyed this way on 2026-10-09.
_HARNESS_SHELL_ENV: tuple[tuple[str, str], ...] = (
    ("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1"),
    ("BASH_DEFAULT_TIMEOUT_MS", "600000"),
    ("BASH_MAX_TIMEOUT_MS", "3600000"),
)

# The `local` settings source, inside the sandbox. The Claude harness resolves it
# relative to the project directory, which is the clone root on both engines.
SANDBOX_HARNESS_SETTINGS_PATH = "/workspace/.claude/settings.local.json"

# Prefixes every line the projection emits, so a line in a prepare-step log is
# attributable to this projection rather than to whichever of the several
# materialized steps happened to be running.
HARNESS_SETTINGS_MARKER = "livespec-sandbox-harness-settings"

_ENV_PLACEHOLDER = "LIVESPEC_HARNESS_SETTINGS_ENV_DECLARATION"
_MARKER_PLACEHOLDER = "LIVESPEC_HARNESS_SETTINGS_MARKER_DECLARATION"

# The stdlib-only merge program, substituted host-side and run by the prepare
# step below. Written as the SHIPPED BYTES rather than as a host-side
# implementation with a sandbox twin: a twin would be a second account of one
# merge, and the two would diverge in the direction that is invisible, since both
# would look correct and only the one the sandbox runs would decide anything.
_MERGE_PROGRAM = """import json
import pathlib
import sys

ENV = LIVESPEC_HARNESS_SETTINGS_ENV_DECLARATION
MARKER = LIVESPEC_HARNESS_SETTINGS_MARKER_DECLARATION

path = pathlib.Path(sys.argv[1])
document = {}
text = path.read_text(encoding="utf-8") if path.is_file() else ""
if text.strip():
    try:
        loaded = json.loads(text)
    except ValueError:
        loaded = None
    if isinstance(loaded, dict):
        document = loaded
    else:
        sys.stderr.write(
            MARKER + ": " + str(path) + " held no JSON object, so its other"
            " content was not preserved\\n"
        )
inherited = document.get("env")
merged = dict(inherited) if isinstance(inherited, dict) else {}
merged.update(ENV)
document["env"] = merged
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(document, indent=2) + "\\n", encoding="utf-8")
sys.stdout.write(MARKER + ": " + str(path) + "\\n")
"""


def harness_shell_env_lines() -> str:
    """Render the harness shell-tool policy as `[environments.<id>.env]` lines.

    Named rather than inlined so the keys and their values have ONE spelling a
    test can bind, the way `tmux_tmpdir_prepare_steps_block` does for the tmux
    socket root. Each value is `json.dumps`-ed for the same reason every other
    line in that table is: the table is TOML, and a value written raw is a
    parse hazard rather than a string.
    """
    return "".join(f"{name} = {json.dumps(value)}\n" for name, value in _HARNESS_SHELL_ENV)


def harness_settings_merge_program() -> str:
    """The merge program, carrying the policy keys as the members it will write.

    The declaration is substituted into the program text rather than passed as an
    argument, for two reasons. The rendered run config is the artifact an operator
    reads when a dispatch's shell calls were capped unexpectedly, so the ceilings
    have to be legible in it rather than hidden behind a base64 payload or an
    argv the log does not carry. And the program then needs exactly one operand,
    the destination path, which the shell resolves once.

    `json.dumps` with an indent keeps the declaration a readable Python literal
    (a JSON object of strings IS one), and it is also what guarantees the
    substituted text cannot close the heredoc or the TOML string that carry it.
    """
    declared = json.dumps(dict(_HARNESS_SHELL_ENV), indent=4)
    return _MERGE_PROGRAM.replace(_ENV_PLACEHOLDER, declared).replace(
        _MARKER_PLACEHOLDER,
        json.dumps(HARNESS_SETTINGS_MARKER),
    )


def harness_settings_prepare_steps_block() -> str:
    """Render the exclude + write `[[run.prepare.steps]]` blocks for the settings file.

    The EXCLUDE step comes first, and its position is load-bearing for the same
    reason it is at the sibling call sites: the Petri-era engine runs each prepare
    step as a graph node and checkpoints after it, so a step that writes inside
    the clone before the exclusion is in place is a step whose checkpoint commits
    what it wrote. The path IS inside the clone on that engine, where the clone is
    `/workspace` itself. This fleet's repositories already gitignore
    `.claude/settings.local.json`, which would cover it here -- but that is a
    fact about the GOVERNED repository's own file, and the overlay serves
    repositories that have made no such commitment, so the exclusion is what
    makes the projection safe without depending on one.

    ONE FILE is named, not the `.claude` directory around it: that directory is
    one a governed repository legitimately tracks (its committed settings, its
    hooks), and excluding it would hide the repository's own content from git.

    The write runs under `python3` rather than in shell, because the merge reads
    a JSON document the sandbox may already carry and preserving its other keys
    is the whole difference between this and an overwrite. `python3` is already a
    hard dependency of this prepare chain -- the plugin-cache gate executes under
    it -- so this adds no new one.
    """
    exclude = worktree_exclude_script(
        paths=(SANDBOX_HARNESS_SETTINGS_PATH,),
        label=HARNESS_SETTINGS_MARKER,
    )
    script = (
        "set -eu\n"
        f'settings="{SANDBOX_HARNESS_SETTINGS_PATH}"\n'
        'mkdir -p "$(dirname "$settings")"\n'
        "python3 - \"$settings\" <<'PY'\n"
        f"{harness_settings_merge_program()}"
        "PY"
    )
    lines = [
        "",
        "# --- Dispatcher-materialized harness settings: the sandbox agent loads",
        "# --- the governed repo's own project settings, whose `env` outranks the",
        "# --- process environment, so the ceilings are declared as a FILE too;",
        "# --- hide it from the run's worktree, then merge it ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(exclude)}",
        "",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"

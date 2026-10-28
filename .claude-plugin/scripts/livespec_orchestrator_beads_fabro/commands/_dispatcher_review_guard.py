"""Materialize the guard that keeps the `review` turn a grading turn.

Work-item `bd-ib-azxvoo`. Measured on run 01M5Y3EGXZSS (work-item `bd-ib-davaxq`,
orchestrator v0.243.14, 2026-10-27): implement, `review@1`, the recapture route
and `proof_capture@2` all succeeded, then `review@2` waited on a process, ran
`git rebase origin/master` and `mise exec -- just check`, and the check never
returned inside the node's 1800 s turn allowance. The run ended at `needs_human`
with no verdict although the work was done. Nothing stopped the reviewer from
doing implement and janitor work: the commit hooks and the post-merge janitor
already own the whole-suite gate, and a rebase belongs to `pr_refresh`.

THE LEVER IS THE HARNESS'S OWN HOOK SURFACE, for the reason
`_dispatcher_plugin_cache_gate` records for its re-entry: the sandbox agent loads
`settings.local.json` and runs its `PreToolUse` hooks before every Bash call. The
`review` node's launch command carries `LIVESPEC_AGENT_STAGE=review`
(`_dispatcher_graph_adapters`), which the hook inherits, so ONE materialized
program can serve every ACP node and bind only the stage whose role it protects.
A prompt instruction alone is what the reviewer already had.

THE REFUSAL IS THE ONE PLACE THIS PROJECTION EXITS 2. The engine reads a
`PreToolUse` hook's exit code 2 as a blocking error and shows the hook's stderr
to the model, which is what lets a refused turn go on to emit its verdict label
within its allowance instead of ending on the turn timeout. Every other failure
mode stays NON-blocking: the declared command runs the program only when it is
on disk, and an unreadable payload exits 0, because `python3 <missing file>`
also exits 2 and would otherwise convert a provisioning fault into a turn whose
every shell call is refused.

THE MATCHER IS A COMMAND-POSITION READ, not a substring search. It splits the
command at unquoted shell separators, unwraps `env`, `sudo`, `timeout`, `mise
exec --`, `uv run` and `sh -c`, reads a command substitution as its own command,
and drops heredoc bodies, so `git rebase` inside a quoted argument, a comment, or
the body of a review record being written to a file is not a rebase. It is a
guard against an honest reviewer overreaching, not a sandbox against an
adversary; an interpreter running a script that rebases is out of its reach.

STDLIB-ONLY, with no livespec import, because the sandbox clone is the governed
repository and carries no copy of this package -- the same reason
`_dispatcher_commit_runner_program` gives.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
    payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "REVIEW_GUARD_HOOK_EVENT",
    "REVIEW_GUARD_HOOK_MATCHER",
    "REVIEW_GUARD_HOOK_TIMEOUT_SECONDS",
    "REVIEW_GUARD_PROGRAM_FILENAME",
    "REVIEW_GUARD_REFUSED_MARKER",
    "REVIEW_GUARD_STAGE",
    "review_guard_hook_declaration",
    "review_guard_prepare_steps_block",
    "review_guard_program_source",
]

REVIEW_GUARD_PROGRAM_FILENAME = "livespec-review-guard.py"
REVIEW_GUARD_REFUSED_MARKER = "LIVESPEC_REVIEW_GUARD_REFUSED"
REVIEW_GUARD_STAGE = "review"
REVIEW_GUARD_HOOK_EVENT = "PreToolUse"
REVIEW_GUARD_HOOK_MATCHER = "Bash"

# Orders of magnitude above what a string match takes; it exists so a
# pathological filesystem cannot hold a tool call open.
REVIEW_GUARD_HOOK_TIMEOUT_SECONDS = 15

_MARKER_PLACEHOLDER = "__REFUSED_MARKER__"
_STAGE_PLACEHOLDER = "__REVIEW_STAGE__"

_PROGRAM_SOURCE = r'''#!/usr/bin/env python3
"""Refuse the commands a grading turn must not run. Rewritten on every dispatch."""
import json
import os
import re
import shlex
import sys

MARKER = "__REFUSED_MARKER__"
STAGE = "__REVIEW_STAGE__"
BRANCH = "branch"
SUITE = "suite"
SUITE_RUNNER = "livespec-implement-check-suite"
MESSAGES = {
    BRANCH: (
        MARKER + ": stage=" + STAGE + " refused a command that moves or edits the run"
        " branch. The review turn grades the published diff and the latest recorded"
        " proof; it makes no branch edits (no rebase, commit, push, merge, reset or"
        " checkout). A rebase belongs to pr_refresh and a commit to implement or"
        " review_fix. Read the change with git diff, git log and git show, then emit"
        " your verdict label."
    ),
    SUITE: (
        MARKER + ": stage=" + STAGE + " refused a whole-suite check. The review turn"
        " runs no whole-suite check: the commit hooks and the post-merge janitor"
        " already own that gate, and it can outlast your turn allowance. If a claim"
        " needs a test, run only a named test id (for example: mise exec -- pytest"
        " tests/path.py::test_name). Emit your verdict label now rather than waiting"
        " on a long command."
    ),
}
BRANCH_MOVERS = frozenset({
    "rebase", "commit", "push", "merge", "reset", "cherry-pick", "revert", "am",
    "pull", "checkout", "switch", "restore", "update-ref", "clean", "apply", "add",
    "rm", "mv", "filter-branch",
})
BRANCH_EDIT_FLAGS = frozenset({
    "-d", "-D", "-m", "-M", "-c", "-C", "-f", "-u", "--delete", "--move", "--copy",
    "--force", "--set-upstream-to", "--unset-upstream",
})
GIT_VALUE_OPTIONS = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
})
JUST_VALUE_OPTIONS = frozenset({
    "-f", "--justfile", "-d", "--working-directory", "--shell", "--chooser",
    "--color", "--command-color", "--dump-format", "--unstable",
})
WRAPPER_VALUE_OPTIONS = {
    "env": frozenset({"-u", "-C", "-S"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-R"}),
    "nice": frozenset({"-n"}),
    "ionice": frozenset({"-c", "-n", "-p"}),
    "timeout": frozenset({"-s", "-k"}),
    "xargs": frozenset({"-n", "-I", "-L", "-P", "-s", "-d", "-E"}),
    "nohup": frozenset(),
    "setsid": frozenset(),
    "stdbuf": frozenset(),
    "command": frozenset(),
    "exec": frozenset(),
    "builtin": frozenset(),
    "time": frozenset(),
}
UV_VALUE_OPTIONS = frozenset({
    "--with", "--python", "-p", "--directory", "--project", "--group", "--extra",
})
KEYWORDS = frozenset({"!", "if", "then", "elif", "else", "while", "until", "do"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
SEPARATORS = ";&|\n()`{}"
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
MAX_DEPTH = 4


def strip_heredocs(text):
    """The command text without heredoc bodies, which are data and not commands."""
    kept = []
    terminator = None
    for line in text.replace("\\\n", " ").split("\n"):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        kept.append(line)
        opener = HEREDOC.search(line)
        if opener is not None and "<<<" not in line:
            terminator = opener.group(2)
    return "\n".join(kept)


def segments(text):
    """The simple-command segments of one text, split at unquoted separators."""
    parts = []
    current = []
    quote = None
    index = 0
    while index < len(text):
        char = text[index]
        index += 1
        if char == "\\" and quote != "'" and index < len(text):
            current.append(char + text[index])
            index += 1
        elif quote is not None:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char in SEPARATORS:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part for part in parts if part.strip()]


def words_of(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def skip_options(rest, value_options):
    """`rest` without its leading options, an option in `value_options` taking a value."""
    index = 0
    while index < len(rest):
        word = rest[index]
        if word in value_options:
            index += 2
        elif (word.startswith("-") and len(word) > 1) or ASSIGNMENT.match(word):
            index += 1
        else:
            break
    return rest[index:]


def git_refusal(rest):
    rest = skip_options(rest, GIT_VALUE_OPTIONS)
    if not rest:
        return None
    subcommand, args = rest[0], rest[1:]
    if subcommand in BRANCH_MOVERS:
        return BRANCH
    if subcommand == "stash":
        return None if args[:1] in (["list"], ["show"]) else BRANCH
    if subcommand == "branch":
        edits = [a for a in args if a in BRANCH_EDIT_FLAGS or a.startswith("--set-upstream-to=")]
        return BRANCH if edits else None
    return None


def just_refusal(rest):
    rest = skip_options(rest, JUST_VALUE_OPTIONS)
    return SUITE if rest[:1] == ["check"] else None


def shell_script(rest):
    """The script a `sh -c`-style invocation carries, or None."""
    for index, word in enumerate(rest[:-1]):
        if word.startswith("-") and not word.startswith("--") and "c" in word:
            return rest[index + 1]
    return None


def refusal_of(words, depth):
    """The refusal kind one simple command earns, or None."""
    while words:
        if ASSIGNMENT.match(words[0]) or words[0] in KEYWORDS:
            words = words[1:]
            continue
        name = os.path.basename(words[0])
        rest = words[1:]
        if name in WRAPPER_VALUE_OPTIONS:
            rest = skip_options(rest, WRAPPER_VALUE_OPTIONS[name])
            words = rest[1:] if name == "timeout" else rest
        elif name in ("mise", "uv") and rest[:1] in (["exec"], ["x"], ["run"]):
            after = rest[1:]
            if "--" in after:
                words = after[after.index("--") + 1:]
            else:
                words = skip_options(after, UV_VALUE_OPTIONS)
        elif name in SHELLS:
            script = shell_script(rest)
            return None if script is None else refusal_in(script, depth + 1)
        elif name == "git":
            return git_refusal(rest)
        elif name == "just":
            return just_refusal(rest)
        elif name == SUITE_RUNNER:
            return SUITE
        else:
            return None
    return None


def refusal_in(text, depth):
    """The first refusal kind a command text earns, reading nested commands too."""
    if depth > MAX_DEPTH:
        return None
    stripped = strip_heredocs(text)
    for segment in segments(stripped):
        kind = refusal_of(words_of(segment), depth)
        if kind is not None:
            return kind
    for nested in SUBSTITUTION.findall(stripped):
        kind = refusal_in(nested[0] or nested[1], depth + 1)
        if kind is not None:
            return kind
    return None


def main(stdin_text, environ, stderr):
    """The hook protocol: 2 refuses the call and shows stderr to the model, 0 allows."""
    if environ.get("LIVESPEC_AGENT_STAGE") != STAGE:
        return 0
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return 0
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0
    kind = refusal_in(command, 0)
    if kind is None:
        return 0
    stderr.write(MESSAGES[kind] + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.stdin.read(), os.environ, sys.stderr))
'''


def review_guard_program_source() -> str:
    """The guard program with its two deployment-time tokens substituted in."""
    return _PROGRAM_SOURCE.replace(_MARKER_PLACEHOLDER, REVIEW_GUARD_REFUSED_MARKER).replace(
        _STAGE_PLACEHOLDER, REVIEW_GUARD_STAGE
    )


def _program_path_expansion() -> str:
    return f"{sandbox_plugins_root_expansion()}/{REVIEW_GUARD_PROGRAM_FILENAME}"


def review_guard_hook_declaration() -> dict[str, list[dict[str, object]]]:
    """The `PreToolUse` Bash hook that runs the guard before every shell call.

    The program runs only when it is on disk. A bare `python3 <missing file>` exits
    2, the blocking status, so without the existence test a sandbox whose prepare
    pass never landed the guard would refuse every shell call of every stage.
    """
    command = f'p="{_program_path_expansion()}"; if test -f "$p"; then exec python3 "$p"; fi'
    return {
        REVIEW_GUARD_HOOK_EVENT: [
            {
                "matcher": REVIEW_GUARD_HOOK_MATCHER,
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": REVIEW_GUARD_HOOK_TIMEOUT_SECONDS,
                    }
                ],
            }
        ]
    }


def review_guard_prepare_steps_block() -> str:
    """Render the prepare step that writes the guard before any ACP stage runs."""
    root = sandbox_plugins_root_expansion()
    step = PrepareStep(
        script=f'set -eu\nmkdir -p "{root}"\n'
        + payload_write_command(path_word=f'"{_program_path_expansion()}"'),
        env={PAYLOAD_ENV_VAR: review_guard_program_source()},
    )
    return "\n# --- Dispatcher-materialized review-turn guard (bd-ib-azxvoo) ---\n" + (
        render_prepare_step(step=step)
    )

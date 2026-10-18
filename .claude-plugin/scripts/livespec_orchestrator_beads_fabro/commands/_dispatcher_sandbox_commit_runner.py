"""Materialize the detached commit runner every committing ACP stage uses.

WHY A DETACHED COMMIT RUNNER AT ALL. An implement-stage agent's `git commit`
fires the governed repository's whole commit gate inside the factory sandbox.
On a loaded host that gate runs longer than one of the agent's tool calls, and
when the limit ends the call the agent is left with NOTHING -- no exit status,
no hook output, no verdict. That kill is indistinguishable from a hook REFUSAL,
so the honest reading of it is "there is no verdict", and a run that cannot tell
the two apart loses verified work with nothing published. Measured on hp run
01M4XWYERJEZ15GNMGHV66CSBY: two `git commit --amend --no-edit` tool calls ended
at 1202366 ms and 1203117 ms with the pre-commit aggregate still running, the
run ended at needs_human, and the SAME amend took 41 minutes when a human
finished it by hand on that host.

Raising the tool-call limit is NOT the fix, and that is the whole reason this
module exists rather than a configuration key. How long the gate runs depends
on the host's load, so any ceiling is a bet against a number nobody controls;
what has to change is that the commit's OUTCOME stops depending on one tool
call at all.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN A PROMPT. The runner is a
PROGRAM whose run directory is written by the commit's own process, because
every state word it reports has to be derivable from records the WAITING agent
did not write -- that is what makes `no-verdict` honest rather than optimistic.
Shell assembled per invocation in a prompt puts that property one paraphrase
away from being lost, and the paraphrase that loses it reports a pass.

WHY NOT THE WORKTREE PACK'S GATE RUNNER. `gate-run.sh` in
livespec-dev-tooling's worktree pack is the design this follows -- a detached
session, a run directory whose exit-status file is written only on real
completion, a signal death and a vanished process both reading as no verdict.
It cannot be the MECHANISM here: it is gitignored and package-installed, so it
reaches a clone only through `just install-worktree-pack`, and this runner has
to work in the sandbox of ANY target repository, including one that carries
none of this fleet's tooling. So the design is reused and the artifact is not.

The program is materialized below the sandbox plugins root at prepare time, the
way `_dispatcher_publication_push` already materializes its push helper, and it
rides the same prepare block for the reason that module records: every
Dispatcher-materialized helper lands below ONE root, so a sandbox given a
subset fails closed at a stage whose refusal would otherwise name the wrong
seam.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "SANDBOX_COMMIT_RUNNER_FILENAME",
    "sandbox_commit_runner_path_expansion",
    "sandbox_commit_runner_prepare_steps_block",
    "sandbox_commit_runner_source",
]

SANDBOX_COMMIT_RUNNER_FILENAME = "livespec-sandbox-commit"

_HEREDOC_DELIMITER = "LIVESPEC_SANDBOX_COMMIT_RUNNER"

# A RAW string: the program's own `printf '%s\n'` calls and its line
# continuations are bytes the shell must receive, not escapes Python should
# resolve before the heredoc ever writes them.
_PROGRAM_SOURCE = r"""#!/bin/sh
#
# livespec-sandbox-commit -- run ONE `git commit` in a detached session and
# report a durable verdict, so a repository commit hook that outlasts the
# agent's per-tool-call limit still reaches its OWN verdict.
#
# WHY THIS EXISTS. An implement-stage agent's `git commit` fires the governed
# repository's whole commit gate. On a loaded factory host that gate can run
# longer than one of the agent's tool calls, and when the limit ends the call
# the agent sees NOTHING: no exit status, no hook output, no verdict. That kill
# is indistinguishable from a hook REFUSAL, and verified work is lost with
# nothing published.
#
# This runner decouples the commit's RUNTIME from the tool call's PATIENCE. It
# weakens no gate: the SAME argv runs, the SAME hooks fire, the commit's own
# exit status is the verdict and this runner only transports it -- and a run
# that does not finish can NEVER read as a pass, because it reports the
# dedicated `no-verdict` state instead.
#
# THE RUN DIRECTORY IS THE EVIDENCE, and it is written by the commit run's own
# process rather than by the waiting agent:
#
#   started_at   written before the commit starts  -> "a run was launched"
#   pid          written by the child itself       -> "the run has a live process"
#   output.log   streamed as the commit runs       -> "these hooks ran"
#   exit_code    written ONLY on real completion   -> "there is a verdict"
#   head_after   written only when the status is 0 -> "this commit resulted"
#
# `exit_code` present is the ONE marker that a verdict exists. Every state is
# derived from those files plus a liveness probe, with no ambiguity left:
#
#   exit_code == 0            -> passed      (and head_after names the commit)
#   exit_code 1..127          -> failed      (a real verdict: a hook refused)
#   exit_code >= 128          -> no-verdict  (killed by signal N=code-128)
#   no exit_code, pid alive   -> running
#   no exit_code, pid dead    -> no-verdict  (vanished before recording one)
#
# USAGE
#   livespec-sandbox-commit start -- <argv that runs a git commit>
#       Mints a run id, launches the commit detached, prints the id on stdout
#       and returns in well under a second. Safe to run in the FOREGROUND.
#
#   livespec-sandbox-commit wait <run-id> <bound-seconds>
#       Blocks for AT MOST <bound-seconds>, then reports `running` or the
#       terminal state. Repeatable any number of times, in any later tool
#       call; it only READS the run directory, so it never disturbs the run.
#
#   livespec-sandbox-commit status <run-id>     one-shot report, never blocks
#   livespec-sandbox-commit stop <run-id>       end a run that must not finish
#
# EXIT STATUS (the STATE WORD on stdout is the contract; this is a convenience)
#   0        passed
#   1..127   failed -- the commit process's own exit status, passed through
#   69       still running when the caller's bound elapsed
#   73       refused: another commit run in this sandbox is still running
#   75       no-verdict -- not a pass and not a failing verdict
#   64       usage error
#   70       the runner itself could not launch the commit
#
# `set -eu`: a runner whose own bookkeeping fails part-way MUST NOT go on to
# write a verdict file, because a half-written run directory is exactly the
# ambiguity this program exists to remove. The one place errexit is suspended
# is around the commit invocation itself, where a non-zero exit IS the payload.
set -eu

EX_USAGE=64
EX_SOFTWARE=70
EX_RUNNING=69
EX_BUSY=73
EX_NO_VERDICT=75
SIGNAL_EXIT_FLOOR=128
POLL_SECONDS=5
OUTPUT_TAIL_LINES=40

usage() {
    echo 'usage: livespec-sandbox-commit start -- <argv that runs a git commit>' >&2
    echo '       livespec-sandbox-commit wait <run-id> <bound-seconds>' >&2
    echo '       livespec-sandbox-commit status <run-id>' >&2
    echo '       livespec-sandbox-commit stop <run-id>' >&2
    exit "$EX_USAGE"
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

epoch_seconds() {
    date -u +%s
}

# Run directories live under the clone's OWN git directory, which is what makes
# "an earlier commit run in the same sandbox" a resolvable question: every
# invocation inside this clone resolves the same store, and nothing outside it
# does. `--absolute-git-dir` rather than `--git-dir`, because the detached child
# resolves this path again from its own session.
runs_root() {
    printf '%s/livespec-commit-runs\n' "$(git rev-parse --absolute-git-dir)"
}

# The state word for a run directory. A pure function of the files on disk plus
# one liveness probe; it writes nothing and signals nothing.
derive_state() {
    derive_dir=$1
    if test ! -d "$derive_dir"; then
        printf 'unknown-run'
        return 0
    fi
    if test -f "$derive_dir/exit_code"; then
        derive_code=$(cat "$derive_dir/exit_code")
        if test "$derive_code" -eq 0; then
            printf 'passed'
        elif test "$derive_code" -ge "$SIGNAL_EXIT_FLOOR"; then
            printf 'no-verdict'
        else
            printf 'failed'
        fi
        return 0
    fi
    if test -f "$derive_dir/pid" && kill -0 "$(cat "$derive_dir/pid")" 2>/dev/null; then
        printf 'running'
        return 0
    fi
    # No exit status and no live process. Either the child was killed before it
    # could record a verdict, or it never got far enough to publish its pid.
    # Both are the same thing to a caller: there is no verdict and none is
    # coming.
    printf 'no-verdict'
}

state_exit_status() {
    status_dir=$1
    status_state=$2
    case "$status_state" in
        passed) printf '0' ;;
        failed) cat "$status_dir/exit_code" ;;
        running) printf '%s' "$EX_RUNNING" ;;
        *) printf '%s' "$EX_NO_VERDICT" ;;
    esac
}

report() {
    report_dir=$1
    report_state=$2
    printf 'state: %s\n' "$report_state"
    printf 'run: %s\n' "$(basename "$report_dir")"
    printf 'command: %s\n' "$(tr '\n' ' ' < "$report_dir/command" 2>/dev/null || true)"
    if test -f "$report_dir/exit_code"; then
        printf 'exit_status: %s\n' "$(cat "$report_dir/exit_code")"
    else
        printf 'exit_status: none recorded\n'
    fi
    printf 'head_before: %s\n' "$(cat "$report_dir/head_before" 2>/dev/null || printf unknown)"
    if test "$report_state" = passed; then
        printf 'head: %s\n' "$(cat "$report_dir/head_after" 2>/dev/null || printf unknown)"
    fi
    printf 'output_log: %s\n' "$report_dir/output.log"
    printf -- '--- final output lines ---\n'
    tail -n "$OUTPUT_TAIL_LINES" "$report_dir/output.log" 2>/dev/null || true
}

# The id of the one commit run in this sandbox that is still `running`, or
# nothing at all.
running_run_id() {
    busy_root=$1
    for busy_dir in "$busy_root"/*; do
        test -d "$busy_dir" || continue
        if test "$(derive_state "$busy_dir")" = running; then
            basename "$busy_dir"
            return 0
        fi
    done
    return 0
}

# Sets RUN_DIR, or exits. Deliberately NOT a value-printing function used in a
# command substitution: `exit` inside one ends the SUBSHELL, so a refusal would
# be captured as the variable's value and the caller would carry on.
resolve_run_dir() {
    resolve_id=$1
    case "$resolve_id" in
        "" | */* | .*)
            echo "livespec sandbox commit: '$resolve_id' is not a commit run id" >&2
            exit "$EX_USAGE"
            ;;
    esac
    RUN_DIR="$(runs_root)/$resolve_id"
    if test ! -d "$RUN_DIR"; then
        printf 'state: unknown-run\nrun: %s\n' "$resolve_id"
        echo "livespec sandbox commit: this sandbox has no commit run $resolve_id" >&2
        exit "$EX_USAGE"
    fi
}

cmd_start() {
    if test "${1:-}" = --; then
        shift
    fi
    test "$#" -ge 1 || usage
    # The argv must RUN A GIT COMMIT. This is a shape check that alters nothing
    # -- the argv is executed exactly as given -- and it is what keeps this
    # program from becoming a general-purpose way to background a tool call:
    # the detached commit run is the ONE exception a committing stage's prompt
    # makes to its rule against backgrounding, so the runner must not be able
    # to carry anything else.
    saw_git=no
    saw_commit=no
    for word in "$@"; do
        if test "$word" = git; then
            saw_git=yes
        elif test "$word" = commit && test "$saw_git" = yes; then
            saw_commit=yes
        fi
    done
    if test "$saw_commit" = no; then
        printf '%s %s\n' \
            'livespec sandbox commit: the argv must run a git commit (a `git` word' \
            'followed by a `commit` word); this runner carries commits and nothing else' >&2
        exit "$EX_USAGE"
    fi

    start_root="$(runs_root)"
    mkdir -p "$start_root"
    busy="$(running_run_id "$start_root")"
    if test -n "$busy"; then
        printf '%s %s %s\n' \
            "livespec sandbox commit: refusing to start -- commit run $busy in this" \
            'sandbox is still running; wait on it until it is terminal, or stop it,' \
            'before starting another' >&2
        exit "$EX_BUSY"
    fi

    run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    attempt=0
    while test -d "$start_root/$run_id"; do
        attempt=$((attempt + 1))
        run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-$attempt"
    done
    start_dir="$start_root/$run_id"
    mkdir -p "$start_dir"
    timestamp > "$start_dir/started_at"
    pwd > "$start_dir/cwd"
    git rev-parse HEAD > "$start_dir/head_before" 2>/dev/null \
        || printf 'unknown\n' > "$start_dir/head_before"
    # One argument per line: the record shows exactly what ran, with no
    # re-quoting guesswork when it is read back later.
    printf '%s\n' "$@" > "$start_dir/command"
    : > "$start_dir/output.log"

    self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    # setsid puts the commit in its OWN session, so the harness killing the
    # tool call's process group cannot reach it. Without this the whole point
    # is lost: the commit would die with the tool call exactly as it does now.
    if command -v setsid > /dev/null 2>&1; then
        setsid "$self" __child "$start_dir" "$@" < /dev/null > /dev/null 2>&1 &
    else
        nohup "$self" __child "$start_dir" "$@" < /dev/null > /dev/null 2>&1 &
    fi

    # The child publishes its own pid as its first act. Waiting briefly for
    # that file means `start` never returns an identity for a commit that
    # failed to launch.
    waited=0
    while test ! -f "$start_dir/pid" \
        && test ! -f "$start_dir/exit_code" \
        && test "$waited" -lt 100; do
        sleep 0.1
        waited=$((waited + 1))
    done
    if test ! -f "$start_dir/pid" && test ! -f "$start_dir/exit_code"; then
        printf '%s %s\n' \
            'livespec sandbox commit: the commit run never published a pid;' \
            "run directory: $start_dir" >&2
        exit "$EX_SOFTWARE"
    fi

    echo ":: commit run $run_id launched detached; this tool call no longer bounds it" >&2
    echo ":: verdict : livespec-sandbox-commit wait $run_id <bound-seconds>  (repeatable)" >&2
    echo ":: output  : $start_dir/output.log" >&2
    echo ':: a run that does not finish reports no-verdict; it can never read as a pass' >&2
    printf '%s\n' "$run_id"
}

# __child -- internal. Runs inside the detached session; everything a verdict
# is derived from is written HERE, by the commit's own process.
cmd_child() {
    child_dir=$1
    shift
    cd "$(cat "$child_dir/cwd")"
    printf '%s\n' "$$" > "$child_dir/pid"

    # errexit off for the commit itself: a non-zero exit is the verdict this
    # program exists to capture, not an error in the runner.
    set +e
    "$@" >> "$child_dir/output.log" 2>&1
    child_code=$?
    set -e

    if test "$child_code" -eq 0; then
        git rev-parse HEAD > "$child_dir/head_after" 2>/dev/null \
            || printf 'unknown\n' > "$child_dir/head_after"
    fi
    timestamp > "$child_dir/finished_at"
    # exit_code is written LAST and atomically. Its presence is the sole marker
    # that a verdict exists, so it must never appear early or half-written.
    printf '%s\n' "$child_code" > "$child_dir/exit_code.partial"
    mv "$child_dir/exit_code.partial" "$child_dir/exit_code"
}

cmd_wait() {
    test "$#" -eq 2 || usage
    resolve_run_dir "$1"
    bound=$2
    case "$bound" in
        "" | *[!0-9]*)
            echo "livespec sandbox commit: '$bound' is not a bound in whole seconds" >&2
            exit "$EX_USAGE"
            ;;
    esac
    deadline=$(($(epoch_seconds) + bound))
    while test "$(derive_state "$RUN_DIR")" = running; do
        remaining=$((deadline - $(epoch_seconds)))
        if test "$remaining" -le 0; then
            break
        fi
        if test "$remaining" -lt "$POLL_SECONDS"; then
            sleep "$remaining"
        else
            sleep "$POLL_SECONDS"
        fi
    done
    waited_state="$(derive_state "$RUN_DIR")"
    report "$RUN_DIR" "$waited_state"
    exit "$(state_exit_status "$RUN_DIR" "$waited_state")"
}

cmd_status() {
    test "$#" -eq 1 || usage
    resolve_run_dir "$1"
    status_now="$(derive_state "$RUN_DIR")"
    report "$RUN_DIR" "$status_now"
    exit "$(state_exit_status "$RUN_DIR" "$status_now")"
}

cmd_stop() {
    test "$#" -eq 1 || usage
    resolve_run_dir "$1"
    if test "$(derive_state "$RUN_DIR")" = running; then
        stop_pid="$(cat "$RUN_DIR/pid")"
        # The session id equals the detached child's pid, so the negative form
        # reaches the commit and every hook process it started.
        kill -TERM "-$stop_pid" 2>/dev/null || kill -TERM "$stop_pid" 2>/dev/null || true
        waited=0
        while test "$(derive_state "$RUN_DIR")" = running && test "$waited" -lt 100; do
            sleep 0.1
            waited=$((waited + 1))
        done
    fi
    stopped_state="$(derive_state "$RUN_DIR")"
    report "$RUN_DIR" "$stopped_state"
    exit "$(state_exit_status "$RUN_DIR" "$stopped_state")"
}

test "$#" -ge 1 || usage
verb=$1
shift
case "$verb" in
    start) cmd_start "$@" ;;
    wait) cmd_wait "$@" ;;
    status) cmd_status "$@" ;;
    stop) cmd_stop "$@" ;;
    __child) cmd_child "$@" ;;
    *) usage ;;
esac
"""


def sandbox_commit_runner_source() -> str:
    """The runner's exact bytes; its verdict is the commit's own exit status."""
    return _PROGRAM_SOURCE


def sandbox_commit_runner_path_expansion() -> str:
    """The path the prepare step writes and every committing stage prompt names."""
    return f"{sandbox_plugins_root_expansion()}/{SANDBOX_COMMIT_RUNNER_FILENAME}"


def sandbox_commit_runner_prepare_steps_block() -> str:
    """A quoted-heredoc prepare step that installs the executable runner.

    The delimiter is QUOTED so the shell expands nothing inside the program: its
    body carries `$#`, `$@`, `$$` and a dozen other parameter expansions, every
    one of which an unquoted heredoc would substitute away before the file was
    written.
    """
    root = sandbox_plugins_root_expansion()
    path = f"{root}/{SANDBOX_COMMIT_RUNNER_FILENAME}"
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f"cat > \"{path}\" <<'{_HEREDOC_DELIMITER}'\n"
        f"{sandbox_commit_runner_source()}"
        f"{_HEREDOC_DELIMITER}\n"
        f'chmod 700 "{path}"'
    )
    return (
        "\n# --- Dispatcher-materialized detached commit runner: the ONE route a\n"
        "# --- committing ACP stage takes to a commit whose hook can outlast the\n"
        "# --- agent tool call that started it ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )

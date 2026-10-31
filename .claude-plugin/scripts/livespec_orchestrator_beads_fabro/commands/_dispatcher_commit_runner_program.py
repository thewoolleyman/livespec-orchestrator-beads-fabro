"""Materialize the sandbox commit runner every committing ACP stage is told to use.

`SPECIFICATION/contracts.md` "A commit leg completes past one tool call"
(Scenario 179, work-item `bd-ib-atyefi`). The prepare step below writes
`livespec-commit-runner.py` into the sandbox plugin root, beside the other
Dispatcher-materialized helpers, and the `implement`, `fix` and `review_fix`
prompts direct every commit through it:

- `start -- <git commit argv>` records a run, launches the commit UNCHANGED in
  its own session so it outlives the tool call, and prints the run id without
  waiting. It refuses `--no-verify` (and the bundled `-n`), and refuses while
  an earlier run is still running, naming that run.
- `wait <run-id> --timeout-seconds <n>` blocks for at most `n` seconds and
  prints one JSON report: `running`, or the terminal state with the exit
  status, the resulting `HEAD` on `passed`, and the output's final lines.

THE VERDICT COMES FROM THE COMMIT PROCESS'S OWN RECORDS. The worker that owns
the commit writes the terminal state when the commit exits on its own; a commit
ended by a signal, or a run whose process group is gone without having written
one, reads as `no-verdict` and never as `failed` or `passed`. That is the
distinction the clause draws, and a waiting agent's own view of its tool call
plays no part in it.

STDLIB-ONLY, with no livespec import, because the sandbox clone is the governed
repository and carries no copy of this package -- the same reason
`_dispatcher_hook_limit_program` gives. The Dispatcher reads the reports this
program prints back off the run's recorded tool output through
`_dispatcher_commit_runner_replay`, which drives the in-package
`DetachedCommitRunner` state machine; the report's JSON keys are therefore the
contract between the two halves, and `REPORT_*` below names them once.

IT CHANGES NO ENVIRONMENT. The clause forbids setting any variable that skips
or relaxes a check, so the worker inherits the agent's environment as it is;
stdin is closed only so that a commit that would open an editor fails rather
than waiting forever on a terminal nobody holds.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_node_timeout_cut import (
    NODE_CUT_COMMIT_RUN_SENTINEL,
    NODE_CUT_HOOK_RUN_SENTINEL,
)
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
    "COMMIT_RUNNER_PROGRAM_FILENAME",
    "HOOK_BANNER_PATTERN",
    "REPORT_EXIT_CODE_KEY",
    "REPORT_FAILED_TARGETS_KEY",
    "REPORT_HEAD_KEY",
    "REPORT_HOOK_RAN_KEY",
    "REPORT_OUTPUT_TAIL_KEY",
    "REPORT_RUN_ID_KEY",
    "REPORT_STATE_KEY",
    "commit_runner_prepare_steps_block",
    "commit_runner_program_path_expansion",
    "commit_runner_program_source",
]

COMMIT_RUNNER_PROGRAM_FILENAME = "livespec-commit-runner.py"

# The lefthook banner a hook run prints, `│ 🥊 lefthook v1.13.6  hook: pre-commit │`
# as measured; the hook name varies, the `hook: ` prefix does not. One pattern
# for the direct-commit reader and the sandbox runner, so the two routes cannot
# disagree about whether a hook ran.
HOOK_BANNER_PATTERN = r"\blefthook\b.*\bhook: "

REPORT_RUN_ID_KEY = "run_id"
REPORT_STATE_KEY = "state"
REPORT_EXIT_CODE_KEY = "exit_code"
REPORT_FAILED_TARGETS_KEY = "failed_targets"
REPORT_HEAD_KEY = "head"
REPORT_HOOK_RAN_KEY = "hook_ran"
REPORT_OUTPUT_TAIL_KEY = "output_tail"

_PROGRAM_SOURCE = r'''#!/usr/bin/env python3
"""Keep an ordinary git commit alive after one ACP tool call ends."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

RUNNING = "running"
NO_VERDICT = "no-verdict"
TAIL_LINES = 60
BRIEF_TAIL_LINES = 80
# Worst first: a settled set is described by its least settled run.
SETTLE_ORDER = (RUNNING, "failed", NO_VERDICT, "passed")
# The gate aggregate's own list of failed recipes, ended by the first line that is not one.
FAILED_TARGETS_HEADER = re.compile(r"^Failed targets \(\d+\):\s*$", re.MULTILINE)
FAILED_TARGET_LINE = re.compile(r"^\s+-\s+(\S+)\s*$")
# git commit short options whose value follows them, so a bundle ends there.
VALUE_SHORT_OPTIONS = "mFCct"
# Short options whose OPTIONAL value is attached (`-uno`), so a bundle ends there too.
ATTACHED_VALUE_SHORT_OPTIONS = "uS"
# The repository hook's own banner; a commit whose output lacks it ran no hook.
HOOK_BANNER = re.compile(__HOOK_BANNER__)
# The two lines `cut-settle` prints for the host to read; one spelling, substituted.
CUT_RUN_SENTINEL = "__CUT_RUN_SENTINEL__"
CUT_HOOK_SENTINEL = "__CUT_HOOK_SENTINEL__"
# The hooks a git commit or push runs, by operation.
OPERATION_HOOKS = {
    "commit": ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "post-rewrite"),
    "push": ("pre-push",),
}
# git options whose value is the next word, so the value is not read as the subcommand.
GIT_VALUE_OPTIONS = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path")
TICKS = os.sysconf("SC_CLK_TCK")
STOP_GRACE_SECONDS = 10.0


class RunnerRefusal(Exception):
    """A start or wait the runner declines, with the reason it prints."""


def git_output(*argv):
    result = subprocess.run(["git", *argv], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RunnerRefusal("no git repository resolved for the commit runner")
    return result.stdout.strip()


def runs_directory():
    return Path(git_output("rev-parse", "--git-path", "livespec-commit-runs"))


def state_path(directory, run_id):
    return directory / (run_id + ".json")


def read_record(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def group_alive(group, proc_root="/proc"):
    """True while any non-zombie process of the run's session group remains."""
    if not os.path.isdir(proc_root):
        try:
            os.killpg(group, 0)
        except OSError:
            return False
        return True
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        try:
            raw = Path(proc_root, name, "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        fields = raw[raw.rfind(")") + 2 :].split()
        if len(fields) > 2 and fields[0] != "Z" and fields[2] == str(group):
            return True
    return False


def recorded_state(record):
    state = record.get("state")
    return state if isinstance(state, str) else NO_VERDICT


def settled(path, record):
    """The record and its state, a running run whose processes are gone read as no-verdict.

    A worker writes its verdict and THEN exits, so a group found gone is checked
    against a fresh read of the record: a commit that passed while this reader
    looked is reported passed, never no-verdict.
    """
    if recorded_state(record) != RUNNING:
        return record, recorded_state(record)
    try:
        group = int(path.with_suffix(".pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        # The launch window: the worker exists before its pid file does.
        return record, RUNNING
    if group_alive(group):
        return record, RUNNING
    fresh = read_record(path) or record
    if recorded_state(fresh) != RUNNING:
        return fresh, recorded_state(fresh)
    return fresh, NO_VERDICT


def current_state(path, record):
    return settled(path, record)[1]


def output_tail(path):
    try:
        text = path.with_suffix(".output").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def commit_arguments(command):
    """The arguments after `commit` when `command` is an ordinary git commit, else None."""
    prefix = command[3:] if command[:3] == ["mise", "exec", "--"] else command
    return prefix[2:] if prefix[:2] == ["git", "commit"] else None


def skips_hooks(arguments):
    expects_value = False
    for argument in arguments:
        if expects_value:
            expects_value = False
            continue
        if argument == "--":
            return False
        # git accepts any unambiguous abbreviation of a long option.
        if argument.startswith("--no-v") and "--no-verify".startswith(argument):
            return True
        if argument.startswith("-") and not argument.startswith("--"):
            for position, letter in enumerate(argument[1:], start=1):
                if letter == "n":
                    return True
                if letter in ATTACHED_VALUE_SHORT_OPTIONS:
                    break
                if letter in VALUE_SHORT_OPTIONS:
                    expects_value = position == len(argument) - 1
                    break
    return False


def start(command, program):
    arguments = commit_arguments(command)
    if arguments is None:
        raise RunnerRefusal("the runner starts only an ordinary `git commit` command")
    if skips_hooks(arguments):
        raise RunnerRefusal("the runner never starts a commit that skips its hooks")
    root = git_output("rev-parse", "--show-toplevel")
    directory = runs_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for path in sorted(directory.glob("*.json")):
        record = read_record(path)
        if record is not None and current_state(path, record) == RUNNING:
            raise RunnerRefusal("commit run " + path.stem + " is still running; wait on it first")
    run_id = "commit-" + uuid.uuid4().hex
    path = state_path(directory, run_id)
    write_record(path, {"state": RUNNING, "command": command, "root": root})
    with path.with_suffix(".launch.log").open("w", encoding="utf-8") as log:
        worker = subprocess.Popen(
            [sys.executable, program, "worker", run_id],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    path.with_suffix(".pid").write_text(str(worker.pid) + "\n", encoding="utf-8")
    print(run_id)
    return 0


def worker(run_id):
    path = state_path(runs_directory(), run_id)
    # Written here as well as by `start`, so a start that died after launching
    # this worker cannot leave a run that reads as running forever.
    path.with_suffix(".pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    record = read_record(path) or {}
    command, root = record.get("command"), record.get("root")
    with path.with_suffix(".output").open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode < 0:
        write_record(path, {"state": NO_VERDICT, "signal": -result.returncode})
        return 1
    text = path.with_suffix(".output").read_text(encoding="utf-8", errors="replace")
    terminal = {"state": "passed" if result.returncode == 0 else "failed"}
    terminal["exit_code"] = result.returncode
    terminal["hook_ran"] = HOOK_BANNER.search(text) is not None
    if result.returncode == 0:
        terminal["head"] = git_output("rev-parse", "HEAD")
    write_record(path, terminal)
    return 0


def report(run_id, path, record):
    record, state = settled(path, record)
    payload = {"run_id": run_id, "state": state}
    if state != RUNNING:
        payload["exit_code"] = record.get("exit_code")
        payload["head"] = record.get("head")
        payload["hook_ran"] = record.get("hook_ran") is True
        if state == "failed":
            payload["failed_targets"] = failed_targets(full_output(path))
        payload["output_tail"] = output_tail(path)
    print(json.dumps(payload, sort_keys=True))
    return 0


def wait(run_id, timeout_seconds):
    path = state_path(runs_directory(), run_id)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        record = read_record(path)
        if record is None:
            raise RunnerRefusal("no commit run " + run_id + " is recorded in this repository")
        if current_state(path, record) != RUNNING or time.monotonic() >= deadline:
            return report(run_id, path, record)
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def full_output(path):
    try:
        text = path.with_suffix(".output").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text.replace("\r", "")


def failed_targets(text):
    header = FAILED_TARGETS_HEADER.search(text)
    if header is None:
        return []
    targets = []
    for line in text[header.end() :].splitlines()[1:]:
        match = FAILED_TARGET_LINE.match(line)
        if match is None:
            break
        targets.append(match.group(1))
    return targets


def brief_text(run_id, path, record, state, timeout_seconds):
    """The re-entry brief for the least settled commit run: what it is and what it showed."""
    named = "Commit run " + run_id + ", which the previous turn started through the commit runner"
    named += " and which was still running when that turn ended, "
    if state == "passed":
        return (
            named + "has since PASSED, so its commit exists; HEAD is "
            + str(record.get("head")) + ". Continue from that commit.\n"
        )
    if state == NO_VERDICT:
        return (
            named + "ended without a verdict (its processes are gone with no recorded exit"
            " status), so no commit was made and HEAD is unchanged. Redo that commit"
            " through the runner.\n"
        )
    if state == RUNNING:
        return (
            named + "was STILL RUNNING when the bounded wait of " + str(int(timeout_seconds))
            + " seconds expired, so it has no verdict yet and no commit is known to exist.\n"
        )
    output = full_output(path)
    targets = failed_targets(output)
    tail = "\n".join(output.splitlines()[-BRIEF_TAIL_LINES:])
    return (
        "failed targets: " + (" ".join(targets) if targets else "none") + "\n\n"
        + named + "ended FAILED with exit status " + str(record.get("exit_code"))
        + "; the repository commit hook "
        + ("ran" if record.get("hook_ran") is True else "did not run")
        + ", and no commit was made. Its own error lines (the tail of its recorded output at "
        + str(path.with_suffix(".output")) + "):\n\n" + tail + "\n"
    )


def settle(timeout_seconds, brief_file):
    """Wait out every commit run recorded as running, then brief on the least settled one."""
    directory = runs_directory()
    brief = Path(brief_file)
    live = []
    for path in sorted(directory.glob("*.json")):
        record = read_record(path)
        if record is not None and recorded_state(record) == RUNNING:
            live.append(path)
    if not live:
        brief.unlink(missing_ok=True)
        return 0
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    outcomes = []
    for path in live:
        while True:
            record = read_record(path) or {}
            record, state = settled(path, record)
            if state != RUNNING or time.monotonic() >= deadline:
                break
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        if state == NO_VERDICT:
            # Recorded, so a later settle does not brief this dead run a second time.
            write_record(path, {"state": NO_VERDICT})
        outcomes.append((path, record, state))
    path, record, state = min(outcomes, key=lambda one: SETTLE_ORDER.index(one[2]))
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(
        state + "\n" + brief_text(path.stem, path, record, state, timeout_seconds),
        encoding="utf-8",
    )
    settled_runs = [{"run_id": one.stem, "state": status} for one, _, status in outcomes]
    print(json.dumps({"settled": settled_runs}, sort_keys=True))
    return 0


def terminate(pid, signal_number):
    try:
        os.kill(pid, signal_number)
    except OSError:
        pass


def read_text(path):
    try:
        return Path(path).read_bytes().decode("utf-8", "replace")
    except OSError:
        return None


def process_table(proc_root):
    """{pid: (state, ppid, pgrp, session, start_ticks)} for every process readable now."""
    table = {}
    try:
        names = os.listdir(proc_root)
    except OSError:
        return table
    for name in names:
        if not name.isdigit():
            continue
        raw = read_text(os.path.join(proc_root, name, "stat"))
        if raw is None:
            continue
        fields = raw[raw.rfind(")") + 2 :].split()
        if len(fields) < 20:
            continue
        try:
            ids = (int(fields[1]), int(fields[2]), int(fields[3]), int(fields[19]))
        except ValueError:
            continue
        table[int(name)] = (fields[0], *ids)
    return table


def descendants(table, root):
    children = {}
    for pid, entry in table.items():
        children.setdefault(entry[1], []).append(pid)
    found, pending = [], list(children.get(root, ()))
    while pending:
        pid = pending.pop()
        found.append(pid)
        pending.extend(children.get(pid, ()))
    return found


def argv_of(proc_root, pid):
    raw = read_text(os.path.join(proc_root, str(pid), "cmdline"))
    return [word for word in raw.split("\0") if word] if raw else []


def git_operation(argv):
    """`commit` or `push` when argv is an ordinary `git commit` or `git push`, else None."""
    if not argv or os.path.basename(argv[0]) != "git":
        return None
    index = 1
    while index < len(argv):
        word = argv[index]
        if word in GIT_VALUE_OPTIONS:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return word if word in OPERATION_HOOKS else None
    return None


def hook_run_start(proc_root, table, pid, operation):
    """The EARLIEST start among descendants of `pid` that name one of the operation's hooks.

    NAMING THE HOOK MEANS EITHER OF TWO THINGS: an installed hook that runs its work
    itself carries `hooks/<name>` in argv, and one that ends in `exec <runner> <name>`
    carries the name as an ARGUMENT instead and never carries the path again.
    """
    starts = []
    for child in descendants(table, pid):
        argv = argv_of(proc_root, child)
        text = " ".join(argv)
        if any("hooks/" + name in text or name in argv for name in OPERATION_HOOKS[operation]):
            starts.append(table[child][4])
    return min(starts) if starts else None


def elapsed_ms(proc_root, start_ticks):
    """The hook run's elapsed milliseconds on the boot clock, or None when unmeasurable."""
    raw = read_text(os.path.join(proc_root, "uptime"))
    try:
        uptime = float(raw.split()[0])
    except (AttributeError, IndexError, ValueError):
        return None
    return max(0, int(round((uptime - start_ticks / TICKS) * 1000)))


def live(proc_root, pids):
    table = process_table(proc_root)
    return [pid for pid in pids if pid in table and table[pid][0] != "Z"]


def reap(proc_root, pids):
    """End every listed process still alive: a termination signal, a grace, then a kill."""
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        for pid in live(proc_root, pids):
            terminate(pid, signal_number)
        deadline = time.monotonic() + STOP_GRACE_SECONDS
        while live(proc_root, pids) and time.monotonic() < deadline:
            time.sleep(0.2)
        if not live(proc_root, pids):
            return


def stop_run(path, proc_root):
    """Stop every process of one commit run: its session, its group and its descendants."""
    try:
        group = int(path.with_suffix(".pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    table = process_table(proc_root)
    members = {
        pid for pid, entry in table.items() if entry[0] != "Z" and group in (entry[2], entry[3])
    }
    if group in table:
        members.update(descendants(table, group))
    reap(proc_root, sorted(members))


def in_scope(proc_root, pid, scope):
    """False only for a process whose working directory is READABLE and outside `scope`.

    The pass ends processes, so it is held to the repository it was started in: a git
    operation elsewhere on the host is none of its business. A working directory this
    reader cannot see leaves the process in scope, since a process it cannot read it
    also cannot signal.
    """
    try:
        cwd = os.path.realpath(os.readlink(os.path.join(proc_root, str(pid), "cwd")))
    except OSError:
        return True
    return cwd == scope or cwd.startswith(scope + os.sep)


def reap_hook_runs(proc_root, scope):
    """Name and end every git commit or push in `scope` whose hook run is still executing."""
    table = process_table(proc_root)
    handled = set()
    for pid, entry in sorted(table.items()):
        operation = git_operation(argv_of(proc_root, pid))
        if entry[0] == "Z" or pid in handled or operation is None:
            continue
        if not in_scope(proc_root, pid, scope):
            continue
        start = hook_run_start(proc_root, table, pid, operation)
        if start is None:
            continue
        elapsed = elapsed_ms(proc_root, start)
        if elapsed is not None:
            print(
                CUT_HOOK_SENTINEL + ": operation=" + operation + " hook_elapsed_ms=" + str(elapsed),
                file=sys.stderr,
            )
        tree = [pid, *descendants(table, pid)]
        handled.update(tree)
        reap(proc_root, tree)


def cut_settle(timeout_seconds, proc_root="/proc"):
    """The pass a node-timeout cut owes before its preservation commit.

    Wait out each commit run recorded as running for the one shared bound, STOP any
    still running so none executes beside the preservation commit, name every run's
    state, then name and end any git commit or push whose hook run is still executing.
    """
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    for path in sorted(runs_directory().glob("*.json")):
        record = read_record(path)
        if record is None:
            continue
        record, state = settled(path, record)
        while state == RUNNING and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            record, state = settled(path, read_record(path) or record)
        if state == RUNNING:
            stop_run(path, proc_root)
            state = recorded_state(read_record(path) or record)
        if state in (RUNNING, NO_VERDICT) and recorded_state(read_record(path) or {}) == RUNNING:
            write_record(path, {"state": NO_VERDICT, "stopped": True})
            state = NO_VERDICT
        print(CUT_RUN_SENTINEL + ": run=" + path.stem + " state=" + state, file=sys.stderr)
    reap_hook_runs(proc_root, os.path.realpath(os.getcwd()))
    return 0


def main(argv, program):
    parser = argparse.ArgumentParser(prog="livespec-commit-runner")
    operations = parser.add_subparsers(dest="operation", required=True)
    start_parser = operations.add_parser("start")
    start_parser.add_argument("command", nargs=argparse.REMAINDER)
    wait_parser = operations.add_parser("wait")
    wait_parser.add_argument("run_id")
    wait_parser.add_argument("--timeout-seconds", required=True, type=float)
    settle_parser = operations.add_parser("settle")
    settle_parser.add_argument("--timeout-seconds", required=True, type=float)
    settle_parser.add_argument("--brief-file", required=True)
    cut_parser = operations.add_parser("cut-settle")
    cut_parser.add_argument("--timeout-seconds", required=True, type=float)
    worker_parser = operations.add_parser("worker")
    worker_parser.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        if args.operation == "start":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            return start(command, program)
        if args.operation == "wait":
            return wait(args.run_id, args.timeout_seconds)
        if args.operation == "settle":
            return settle(args.timeout_seconds, args.brief_file)
        if args.operation == "cut-settle":
            return cut_settle(args.timeout_seconds)
        return worker(args.run_id)
    except RunnerRefusal as refusal:
        print("livespec commit runner: " + str(refusal), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], os.path.abspath(__file__)))
'''


def commit_runner_program_source() -> str:
    """The sandbox program's exact bytes, carrying the one hook-banner pattern."""
    return (
        _PROGRAM_SOURCE.replace("__HOOK_BANNER__", repr(HOOK_BANNER_PATTERN))
        .replace("__CUT_RUN_SENTINEL__", NODE_CUT_COMMIT_RUN_SENTINEL)
        .replace("__CUT_HOOK_SENTINEL__", NODE_CUT_HOOK_RUN_SENTINEL)
    )


def commit_runner_program_path_expansion() -> str:
    """The sandbox-local runner path shared by the prepare step and the prompts."""
    return f"{sandbox_plugins_root_expansion()}/{COMMIT_RUNNER_PROGRAM_FILENAME}"


def commit_runner_prepare_steps_block() -> str:
    """Render the prepare step that writes the runner before any ACP stage runs."""
    root = sandbox_plugins_root_expansion()
    path = commit_runner_program_path_expansion()
    step = PrepareStep(
        script=f'set -eu\nmkdir -p "{root}"\n' + payload_write_command(path_word=f'"{path}"'),
        env={PAYLOAD_ENV_VAR: commit_runner_program_source()},
    )
    return (
        "\n# --- Dispatcher-materialized detached commit runner (bd-ib-atyefi) ---\n"
        + render_prepare_step(step=step)
    )

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
import subprocess
import sys
import time
import uuid
from pathlib import Path

RUNNING = "running"
NO_VERDICT = "no-verdict"
TAIL_LINES = 60
# git commit short options whose value follows them, so a bundle ends there.
VALUE_SHORT_OPTIONS = "mFCct"
# Short options whose OPTIONAL value is attached (`-uno`), so a bundle ends there too.
ATTACHED_VALUE_SHORT_OPTIONS = "uS"
# The repository hook's own banner; a commit whose output lacks it ran no hook.
HOOK_BANNER = re.compile(__HOOK_BANNER__)


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


def main(argv, program):
    parser = argparse.ArgumentParser(prog="livespec-commit-runner")
    operations = parser.add_subparsers(dest="operation", required=True)
    start_parser = operations.add_parser("start")
    start_parser.add_argument("command", nargs=argparse.REMAINDER)
    wait_parser = operations.add_parser("wait")
    wait_parser.add_argument("run_id")
    wait_parser.add_argument("--timeout-seconds", required=True, type=float)
    worker_parser = operations.add_parser("worker")
    worker_parser.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        if args.operation == "start":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            return start(command, program)
        if args.operation == "wait":
            return wait(args.run_id, args.timeout_seconds)
        return worker(args.run_id)
    except RunnerRefusal as refusal:
        print("livespec commit runner: " + str(refusal), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], os.path.abspath(__file__)))
'''


def commit_runner_program_source() -> str:
    """The sandbox program's exact bytes, carrying the one hook-banner pattern."""
    return _PROGRAM_SOURCE.replace("__HOOK_BANNER__", repr(HOOK_BANNER_PATTERN))


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

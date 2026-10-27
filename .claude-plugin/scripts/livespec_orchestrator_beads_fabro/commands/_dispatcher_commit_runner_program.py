"""Materialize the durable commit runner used by committing ACP stages."""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "COMMIT_RUNNER_PROGRAM_FILENAME",
    "commit_runner_prepare_steps_block",
    "commit_runner_program_path_expansion",
    "commit_runner_program_source",
]

COMMIT_RUNNER_PROGRAM_FILENAME = "livespec-commit-runner"

# This program deliberately lives in the sandbox plugin cache.  It owns the real
# process; the in-package runner owns the fake-clock state-machine contract, and
# the ACP event reader below uses that same terminal normalizer for the durable
# process's recorded outcome.
_PROGRAM = r'''#!/usr/bin/env python3
"""Keep an ordinary commit alive after one ACP tool wait ends."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


def git_path(name: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", name], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("no git repository resolved for the commit runner")
    return Path(result.stdout.strip())


def state_path(run_id: str) -> Path:
    return git_path("livespec-commit-runs") / (run_id + ".json")


def read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "no-verdict"}
    return value if isinstance(value, dict) else {"state": "no-verdict"}


def write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\\n", encoding="utf-8")
    temporary.replace(path)


def targets(output: str) -> list[str]:
    _, marker, remainder = output.partition("Failed targets")
    return [
        line.strip()[2:].strip()
        for line in remainder.splitlines()
        if marker and line.strip().startswith("- ")
    ]


def report(state: dict[str, object]) -> int:
    output = str(state.get("output", ""))
    print(
        json.dumps(
            {"state": state.get("state", "no-verdict"), "exit_code": state.get("exit_code"),
             "failed_targets": targets(output), "output_tail": output[-4000:]},
            sort_keys=True,
        )
    )
    return 0


def worker(run_id: str) -> int:
    path = state_path(run_id)
    state = read(path)
    command, root = state.get("command"), state.get("root")
    if not isinstance(command, list) or not all(isinstance(one, str) for one in command):
        write(path, {"state": "no-verdict"})
        return 1
    output_path = path.with_suffix(".output")
    with output_path.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command, cwd=root if isinstance(root, str) else None, stdout=output,
            stderr=subprocess.STDOUT, check=False,
        )
    text = output_path.read_text(encoding="utf-8", errors="replace")
    write(
        path,
        {"state": "passed" if result.returncode == 0 else "failed",
         "exit_code": result.returncode, "output": text},
    )
    return result.returncode


def start(command: list[str]) -> int:
    if command[:2] != ["git", "commit"] or "--no-verify" in command:
        raise RuntimeError("the runner accepts an ordinary git commit without --no-verify")
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if root.returncode:
        raise RuntimeError("no git repository resolved for the commit runner")
    directory = git_path("livespec-commit-runs")
    directory.mkdir(parents=True, exist_ok=True)
    if any(read(path).get("state") == "running" for path in directory.glob("*.json")):
        raise RuntimeError("a commit run is still running")
    run_id = "commit-" + uuid.uuid4().hex
    path = state_path(run_id)
    write(path, {"state": "running", "command": command, "root": root.stdout.strip()})
    with path.with_suffix(".launch.log").open("w", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, __file__, "worker", run_id], stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )
    print(run_id)
    return 0


def wait(run_id: str, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = read(state_path(run_id))
        if state.get("state") != "running" or time.monotonic() >= deadline:
            return report(state)
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("command", nargs=argparse.REMAINDER)
    wait_parser = commands.add_parser("wait")
    wait_parser.add_argument("run_id")
    wait_parser.add_argument("--timeout-seconds", required=True, type=float)
    worker_parser = commands.add_parser("worker")
    worker_parser.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        if args.operation == "start":
            return start(args.command)
        if args.operation == "wait":
            return wait(args.run_id, args.timeout_seconds)
        return worker(args.run_id)
    except RuntimeError as error:
        print("livespec commit runner: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def commit_runner_program_source() -> str:
    """The sandbox executable's exact bytes."""
    return _PROGRAM


def commit_runner_program_path_expansion() -> str:
    """The sandbox-local runner path shared by preparation and prompts."""
    return f"{sandbox_plugins_root_expansion()}/{COMMIT_RUNNER_PROGRAM_FILENAME}"


def commit_runner_prepare_steps_block() -> str:
    """Render the prepare step that installs the runner before every ACP stage."""
    root = sandbox_plugins_root_expansion()
    path = commit_runner_program_path_expansion()
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f"cat > \"{path}\" <<'LIVESPEC_COMMIT_RUNNER'\n"
        f"{commit_runner_program_source()}"
        "LIVESPEC_COMMIT_RUNNER\n"
        f'chmod 700 "{path}"\n'
        f'ln -sf "{path}" "/usr/local/bin/{COMMIT_RUNNER_PROGRAM_FILENAME}"'
    )
    return (
        "\n# --- Dispatcher-materialized detached commit runner ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )

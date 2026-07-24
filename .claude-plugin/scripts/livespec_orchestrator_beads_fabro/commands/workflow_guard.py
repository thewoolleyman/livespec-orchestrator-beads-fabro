"""CLI supervisor for the Dispatcher's factory workflow-file guard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard import (
    check_no_workflow_changes,
)

__all__: list[str] = [
    "main",
]


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workflow-guard")
    _ = parser.add_argument("--repo", dest="repo", default=".")
    args = parser.parse_args(argv)
    result = check_no_workflow_changes(
        repo=Path(args.repo),
        runner=ShellCommandRunner(),
    )
    stream = sys.stdout if result.exit_code == 0 else sys.stderr
    _ = stream.write(f"{result.message}\n")
    return result.exit_code

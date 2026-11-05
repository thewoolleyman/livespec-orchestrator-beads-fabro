"""CLI binding for a planned factory restart cancellation."""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cancel_for_restart import (
    cancel_for_restart,
)

__all__: list[str] = ["run_cancel_for_restart_command"]


def add_cancel_for_restart_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Register the arguments accepted by ``cancel-for-restart``."""
    _ = parser.add_argument("--factory", required=True)
    _ = parser.add_argument("--repo")


def run_cancel_for_restart_command(*, args: argparse.Namespace) -> int:
    """Cancel one factory's active runs, preserving janitor-green trees first."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    target = resolve_fabro_factory(cwd=repo, factory=args.factory)
    return cancel_for_restart(
        repo=repo,
        factory=target.name,
        target=target,
        fabro_bin=resolve_fabro_bin(cwd=repo),
    )

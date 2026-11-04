"""Print the installed plugin root registered for one governed project."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    default_plugin_install_registry,
    registered_plugin_root,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = ["main", "run_registered_plugin_root_command"]

_EXIT_MISSING_INSTALL = 3


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print the registry-selected install root for ``--repo``."""
    parser = argparse.ArgumentParser(prog="registered_plugin_root")
    _ = parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args(argv)
    return run_registered_plugin_root_command(repo=args.repo)


def run_registered_plugin_root_command(*, repo: Path) -> int:
    """Emit ``repo``'s registered root, or name the missing registration."""
    install_record = default_plugin_install_registry()
    root = registered_plugin_root(repo=repo, install_record=install_record)
    if root is None:
        _ = write_stderr(
            text=(
                "registered-plugin-root: no registered install of "
                "livespec-orchestrator-beads-fabro for "
                f"{repo} in {install_record}\n"
            )
        )
        return _EXIT_MISSING_INSTALL
    _ = write_stdout(text=f"{root}\n")
    return 0

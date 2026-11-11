"""Materialize the Red and Green command-node programs into the sandbox plugin root."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "COMMIT_GREEN_PROGRAM_FILENAME",
    "COMMIT_RED_PROGRAM_FILENAME",
    "commit_green_command_script",
    "commit_green_program_source",
    "commit_red_command_script",
    "commit_red_program_source",
]

COMMIT_RED_PROGRAM_FILENAME = "livespec-commit-red.sh"
COMMIT_GREEN_PROGRAM_FILENAME = "livespec-commit-green.sh"
_RED_SOURCE_FILENAME = "_dispatcher_commit_red_program.sh"
_GREEN_SOURCE_FILENAME = "_dispatcher_commit_green_program.sh"


def _program_source(*, filename: str) -> str:
    """Read a shipped command program rather than a target-repository file."""
    return Path(__file__).with_name(filename).read_text(encoding="utf-8")


def commit_red_program_source() -> str:
    """Return the complete Red program dispatched into every sandbox."""
    return _program_source(filename=_RED_SOURCE_FILENAME)


def commit_green_program_source() -> str:
    """Return the complete Green program dispatched into every sandbox."""
    return _program_source(filename=_GREEN_SOURCE_FILENAME)


def _program_path_expansion(*, filename: str) -> str:
    return f"{sandbox_plugins_root_expansion()}/{filename}"


def commit_red_command_script() -> str:
    """The command-node script for Red, independent of the target repository."""
    return f'bash "{_program_path_expansion(filename=COMMIT_RED_PROGRAM_FILENAME)}"'


def commit_green_command_script() -> str:
    """The command-node script for Green, independent of the target repository."""
    return f'bash "{_program_path_expansion(filename=COMMIT_GREEN_PROGRAM_FILENAME)}"'

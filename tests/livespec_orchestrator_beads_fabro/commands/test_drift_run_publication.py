"""The drift job publishes its proposals from an isolated worktree."""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_PATH = _COMMANDS / "_drift_run_publication.py"


def test_a_drift_job_publishes_one_pull_request_from_a_fresh_worktree() -> None:
    """The primary checkout is never the proposal-writing venue."""
    assert _MODULE_PATH.is_file()

    publication = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run_publication"
    )

    assert hasattr(publication, "GitDriftRunPublisher")

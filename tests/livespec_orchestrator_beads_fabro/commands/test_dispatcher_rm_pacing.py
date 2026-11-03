"""The Dispatcher's host-wide Fabro deletion-pacing policy."""

from __future__ import annotations

from pathlib import Path


def test_deletion_pacing_has_a_dedicated_dispatcher_module() -> None:
    module = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_rm_pacing.py"
    )

    assert module.is_file()

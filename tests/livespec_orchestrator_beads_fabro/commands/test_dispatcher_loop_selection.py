"""Dispatcher terminal-selection entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)


def test_terminal_selection_entry_point_is_public() -> None:
    assert callable(post_run_dispositions)

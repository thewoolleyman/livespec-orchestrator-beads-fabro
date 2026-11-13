"""Dispatcher loop entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one


def test_dispatch_loop_entry_point_is_public() -> None:
    assert callable(dispatch_one)

"""Dispatcher pre-dispatch wall entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)


def test_pre_dispatch_wall_entry_point_is_public() -> None:
    assert callable(pre_dispatch_wall_exit)

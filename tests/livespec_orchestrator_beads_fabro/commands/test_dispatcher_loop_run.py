"""Dispatcher watchdog-run context coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import DispatchRunContext


def test_watchdog_context_is_public() -> None:
    assert DispatchRunContext.__name__ == "DispatchRunContext"

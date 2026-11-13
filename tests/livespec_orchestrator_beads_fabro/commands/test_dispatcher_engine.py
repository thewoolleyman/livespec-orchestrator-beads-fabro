"""Dispatcher engine entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import run_dispatch


def test_dispatch_engine_is_public() -> None:
    assert callable(run_dispatch)

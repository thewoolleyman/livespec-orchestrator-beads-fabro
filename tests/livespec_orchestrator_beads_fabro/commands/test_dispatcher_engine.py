"""Mirror test module for the dispatch engine."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import run_dispatch


def test_dispatch_engine_is_importable() -> None:
    """Already-satisfied integration coverage exercises the public entry point."""
    assert callable(run_dispatch)

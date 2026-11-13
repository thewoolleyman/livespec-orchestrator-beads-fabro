"""Dispatcher engine-input rendering coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_inputs import (
    dispatch_fabro_run_inputs,
)


def test_engine_input_renderer_is_public() -> None:
    assert callable(dispatch_fabro_run_inputs)

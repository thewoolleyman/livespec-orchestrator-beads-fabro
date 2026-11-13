"""Calibration span entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_span import (
    emit_calibration_span,
)


def test_calibration_span_emitter_is_public() -> None:
    assert callable(emit_calibration_span)

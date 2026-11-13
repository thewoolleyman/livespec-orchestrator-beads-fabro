"""Calibration emission entry-point coverage."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)


def test_calibration_emitter_is_public() -> None:
    assert callable(emit_calibration)

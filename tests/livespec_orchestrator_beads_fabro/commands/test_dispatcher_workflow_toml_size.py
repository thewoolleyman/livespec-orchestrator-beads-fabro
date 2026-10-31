"""The materialized run-config size guard."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_workflow_toml_size.py"
)


def test_build_guard_refuses_a_representative_config_above_ninety_percent() -> None:
    """The release guard reports the measurement, threshold, and engine limit."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_toml_size"
    )
    refusal = module.build_size_refusal(measured_bytes=471_860)
    assert refusal == (
        "materialized workflow.toml is 471860 bytes; build threshold is 471859 bytes; "
        "Fabro limit is 524288 bytes"
    )


@pytest.mark.parametrize("measured_bytes", [0, 463_547, 471_859])
def test_build_guard_reports_and_accepts_a_representative_config_at_or_below_threshold(
    measured_bytes: int,
) -> None:
    """The guard exposes its measured size even when the representative passes."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_toml_size"
    )
    assert module.build_size_refusal(measured_bytes=measured_bytes) is None
    assert module.build_size_report(measured_bytes=measured_bytes) == (
        f"materialized workflow.toml is {measured_bytes} bytes; build threshold is "
        "471859 bytes; Fabro limit is 524288 bytes"
    )

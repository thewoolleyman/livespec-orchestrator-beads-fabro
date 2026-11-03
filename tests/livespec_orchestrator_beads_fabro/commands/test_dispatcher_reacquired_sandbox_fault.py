"""Recognition of a Dispatcher helper missing after sandbox re-acquisition."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "helper",
    [
        "LIVESPEC_PROOF_GRADE_PROGRAM_ABSENT",
        "LIVESPEC_JANITOR_PLUGIN_GATE_FAILED",
        "LIVESPEC_COMMIT_SETTLE_RUNNER_ABSENT",
    ],
)
def test_reacquired_sandbox_helper_absence_is_a_host_fault(helper: str) -> None:
    """Only the measured resume evidence turns a missing helper into a release."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_reacquired_sandbox_fault.py"
    )
    assert module_path.is_file()

    fault = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reacquired_sandbox_fault"
    )
    text = f"{helper}\nfencing a recorded sandbox\nscope environment acquired"

    assert fault.reacquired_sandbox_helper_absence(text=text)
    assert not fault.reacquired_sandbox_helper_absence(text=helper)

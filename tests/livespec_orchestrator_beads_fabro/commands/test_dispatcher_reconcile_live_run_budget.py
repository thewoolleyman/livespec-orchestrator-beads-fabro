"""The recovery effects for an abandoned live run's wall-budget cancel."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_reconcile_live_run_budget.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_live_run_budget"


def test_the_live_run_budget_recovery_module_exposes_the_recovery_route() -> None:
    """The claim lane has a dedicated route, rather than treating it as absent."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE_NAME)

    assert module.ACTION_LIVE_RUN_WALL_BUDGET == "live-run-wall-budget"

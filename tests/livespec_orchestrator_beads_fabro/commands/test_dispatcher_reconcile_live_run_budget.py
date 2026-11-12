"""A reconciliation pass applies the wall budget after an observer vanished."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_live_run_budget"
_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_reconcile_live_run_budget.py"
)


def test_an_unowned_running_claim_past_its_budget_is_a_wall_budget_candidate() -> None:
    """The claim lane must not retain a run merely because the old watcher died."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)

    assert module.should_enforce_wall_budget(
        run_status="running",
        owner_liveness="none",
        elapsed_seconds=3601.0,
        budget_seconds=3600.0,
    )


def test_an_unowned_parked_live_claim_past_its_budget_is_a_wall_budget_candidate() -> None:
    """A live run keeps its slot while parked, not only while executing."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)

    assert module.should_enforce_wall_budget(
        run_status="blocked",
        owner_liveness="none",
        elapsed_seconds=3601.0,
        budget_seconds=3600.0,
    )

"""Terminal outcomes already decided by a Fabro launcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    run_wall_budget_outcome,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
        DispatchOutcome,
        FabroRunResult,
    )

__all__: list[str] = ["launcher_terminal"]


def launcher_terminal(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    launched: FabroRunResult,
) -> DispatchOutcome | None:
    """Return the final outcome already performed by the foreground launcher."""
    if launched.abandoned_run_id is not None:
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="stale-run-reap",
            pr_number=None,
            merge_sha=None,
            detail=(
                f"run {launched.abandoned_run_id} abandoned because work-item "
                f"{plan.work_item_id} status is {launched.abandoned_item_status}; "
                "item is no longer dispatchable"
            ),
            fabro_run_id=launched.abandoned_run_id,
        )
    if launched.budget_exceeded_run_id is not None:
        return run_wall_budget_outcome(
            outcome_type=outcome_type, plan=plan, run_id=launched.budget_exceeded_run_id
        )
    if launched.stalled_run_id is not None:
        return stalled_outcome(outcome_type=outcome_type, plan=plan, run_id=launched.stalled_run_id)
    return None

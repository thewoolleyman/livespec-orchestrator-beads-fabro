"""Terminal outcomes already decided by reattach supervision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    run_wall_budget_outcome,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import DispatchOutcome

__all__: list[str] = ["reattach_terminal"]


def reattach_terminal(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    inspect: FabroInspectResult | None,
) -> DispatchOutcome | None:
    """Return the final disposition already performed by reattach supervision.

    A client that drops moves the watchdog from the launcher into reattach.
    Both routes cancel before returning, so both bypass terminal parsing and
    pull-request flow; only the source object carrying the cancelled run differs.
    """
    if inspect is None:
        return None
    if inspect.budget_exceeded_run_id is not None:
        return run_wall_budget_outcome(
            outcome_type=outcome_type,
            plan=plan,
            run_id=inspect.budget_exceeded_run_id,
        )
    if inspect.stalled_run_id is not None:
        return stalled_outcome(
            outcome_type=outcome_type,
            plan=plan,
            run_id=inspect.stalled_run_id,
        )
    return None

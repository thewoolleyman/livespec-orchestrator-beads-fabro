"""The terminal the LAUNCHER itself ended a run with, as the engine reads it.

Split out of `_dispatcher_engine` by cohesion when that module reached its file LLOC
ceiling: the question "did the launcher already end this run?" is answered from the
launcher's own result alone and shares nothing with the publication flow around it.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    run_wall_budget_outcome,
    stalled_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    DispatchOutcome,
    FabroRunResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = ["launcher_terminal"]


def launcher_terminal(
    *,
    plan: DispatchPlan,
    launched: FabroRunResult,
) -> DispatchOutcome | None:
    """The terminal the LAUNCHER itself ended this run with, or None.

    Three endings reach the engine already decided, because the launcher's own
    watch loop took them: a reaped run whose work-item had stopped being
    dispatchable, a run cancelled past its whole-run wall budget, and a run
    cancelled as stalled. Each is final — the run has been `fabro rm -f`-ed —
    so the engine short-circuits before any PR flow rather than inspecting a
    run that no longer exists.

    THE BUDGET ARM PRECEDES THE STALL ARM, which is the clause's own precedence:
    "When a run's measured budget is exceeded and the run also meets the
    stalled-no-progress rule, the budget takes precedence." A quiet run past its
    budget satisfies both, and only the budget disposition rests it for a person
    — so a stall arm reading first would release an item nothing automatic
    should re-dispatch. The launcher applies the same precedence in its own
    loop; this ordering is the second half of one guarantee rather than a
    duplicate of it, because the two surfaces decide different things: the loop
    decides which cancel to PERFORM and this decides which terminal to REPORT.

    Grouped into one function rather than three returns in `run_dispatch`
    because they are one question — "did the launcher already end this run?" —
    and because reading them as a group is what makes the precedence above
    visible at the point it applies.
    """
    if launched.abandoned_run_id is not None:
        return DispatchOutcome(
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
            outcome_type=DispatchOutcome, plan=plan, run_id=launched.budget_exceeded_run_id
        )
    if launched.stalled_run_id is not None:
        return stalled_outcome(
            outcome_type=DispatchOutcome, plan=plan, run_id=launched.stalled_run_id
        )
    return None

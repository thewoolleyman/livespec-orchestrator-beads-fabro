"""Terminal outcomes that end merge polling without post-merge work."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    MERGE_POLL_BUDGET_EXHAUSTED,
    BaseAdvancedAfterArming,
    merge_poll_budget_exhausted_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_view import view_pr

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = ["outcome_at_exhaustion"]


def outcome_at_exhaustion(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    pr_number: int,
    run_id: str | None,
) -> PrView | DispatchOutcome:
    """Read once more at budget exhaustion before resting the pull request."""
    view = view_pr(plan=plan, runner=runner, journal=journal, include_status_checks=False).view
    if view is not None and view.state == "MERGED":
        return view
    if view is not None and view.state == "OPEN" and view.merge_state_status != "DIRTY":
        return outcome_type(
            work_item_id=plan.work_item_id,
            status="blocked",
            stage="merge-poll",
            pr_number=view.number,
            merge_sha=None,
            detail=merge_poll_budget_exhausted_detail(work_item_id=plan.work_item_id),
            fabro_run_id=run_id,
            base_advanced=BaseAdvancedAfterArming(
                factory=plan.fabro_factory_name,
                pr_head=view.head,
                default_branch_tip=view.base,
                cause=MERGE_POLL_BUDGET_EXHAUSTED,
            ),
        )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="failed",
        stage="merge-poll",
        pr_number=pr_number,
        merge_sha=None,
        detail="PR did not reach MERGED within the poll budget",
        fabro_run_id=run_id,
    )

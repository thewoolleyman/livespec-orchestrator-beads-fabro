"""The merge-containment evidence the `reconcile-merged --regrade` arm keys on.

Split out of `_dispatcher_reconcile_regrade` by cohesion, because that module was at
its size ceiling and this is the one concern in it that is a pure question about the
repository rather than a disposition of the item: whether the merged pull request's
merge commit is an ancestor of the default branch's tip. Only the public entry point,
the stage name and the refusal text cross the module boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    janitor_venue_contains_merge_argv,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "MERGE_CONTAINMENT_STAGE",
    "UNMERGED_REFUSAL",
    "merge_containment_refusal",
]

MERGE_CONTAINMENT_STAGE = "regrade-merge-containment"
_CONTAINMENT_TIMEOUT_SECONDS = 30.0
UNMERGED_REFUSAL = (
    "ERROR: reconcile-merged --regrade refused: no merged PR resolves for work-item "
    "{item_id}, so there is no merged diff to re-grade against. The arm keys on the "
    "merge itself; drive the fix-forward rework re-dispatch instead.\n"
)
_UNCONTAINED_REFUSAL = (
    "ERROR: reconcile-merged --regrade refused: the merge commit {merge_sha} of PR "
    "#{pr_number} for work-item {item_id} is not an ancestor of {tip}, so this "
    "repository cannot show the work landed on the default branch. Fetch {tip} and "
    "retry, or drive the fix-forward rework re-dispatch instead.\n"
)


def merge_containment_refusal(
    *,
    plan: DispatchPlan,
    item: WorkItem,
    merged: PrView,
    runner: CommandRunner,
    journal: JournalFile,
) -> str | None:
    """Refuse unless the resolved merge commit is an ancestor of the default branch.

    The tip is `origin/<default branch>` read off the plan's ONE resolved
    contract, exactly as the janitor venue resolves its own, so the arm and the
    dispatch path cannot come to name two different branches. A commit is its
    own ancestor, so a tip that IS the merge answers yes.

    This is the half of the evidence an operator cannot assert: a forge that
    reports a merged pull request says the pull request merged, while the
    ancestry says THIS repository can see the work on the branch it is about to
    close the item against.
    """
    tip = f"origin/{plan.integration.contract.default_branch}"
    merge_sha = merged.merge_sha
    if merge_sha is None:  # pragma: no cover - resolve_merged_pr yields only sha-bearing views
        return UNMERGED_REFUSAL.format(item_id=item.id)
    contains = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage=MERGE_CONTAINMENT_STAGE,
        command=(
            janitor_venue_contains_merge_argv(plan=plan, tip=tip, merge_sha=merge_sha),
            plan.repo,
            _CONTAINMENT_TIMEOUT_SECONDS,
            None,
        ),
    )
    if contains.exit_code != 0:
        return _UNCONTAINED_REFUSAL.format(
            merge_sha=merge_sha, pr_number=merged.number, item_id=item.id, tip=tip
        )
    return None

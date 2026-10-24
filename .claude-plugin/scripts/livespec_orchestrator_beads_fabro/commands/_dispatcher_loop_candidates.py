"""The drain's CANDIDATE ENUMERATION: which rows one pass may advertise.

Split out of `_dispatcher_loop_selection`, which keeps the readiness PREDICATES
(`ready_items`, `is_dispatch_candidate`) and the pass plumbing. The seam is the
question each side answers: a predicate asks whether ONE row is launchable at
all, while this asks which of the launchable rows THIS pass may pick — a
question that now consumes two independent filters and will consume more.

What pushed it out was the pre-dispatch Definition-of-Done judgement's own
filter, which made this the second composition point in the module and took the
file past its line ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    spec_change_unheld_candidates,
)

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["candidates"]


def candidates(
    *,
    args: argparse.Namespace,
    items: list[WorkItem],
    repo: Path,
) -> list[WorkItem]:
    """The drain's selection for one pass, in the canonical ranked order.

    The AUTONOMOUS pass applies the shared acceptance-eligibility filter, which
    is what the ranking algorithm means by the drain consuming the same filtered
    set as `next`: a legacy row the wall would refuse is never selected, so it
    can neither spend the budget nor stop the queue behind it with a wave-level
    refusal.

    It then drops every row a standing pre-dispatch Definition-of-Done verdict
    REFUSES, which the clause requires "until its effective criteria or
    referenced headings change". That second filter takes no judgement of its
    own: it reads the verdict already recorded, so an unrepaired row cannot stop
    the queue behind it and a drain pass costs no model call per candidate. Both
    filters are handed the SAME `workflow_name`, because both are scoped to an
    implement-kind item and a groom candidate exempted by one of them while the
    other dropped it would be invisible to the drain either way.

    It then drops every row the SPEC-CHANGE TIER mechanically holds out of
    `ready` — a recorded classification of spec-change tier whose linked
    proposed-change topic has not ratified. That third filter spends nothing
    either, and for a sharper reason than the second: the clause makes the hold
    "a read of the spec history" that "needs no model", so a row whose topic HAS
    ratified is deliberately KEPT and decided by the wall's own fresh
    classification instead.

    A NAMED id is narrowed to and deliberately NOT filtered. The clause keeps the
    hand-picked path protected by the wall "even when candidate enumerations
    filtered the item earlier", and that only holds if the named row still
    reaches it — dropping it here would report the drain as having nothing to do
    for an id the operator typed, which is the absence-reads-as-resolution
    failure the attention contract forbids.
    """
    ranked = ready_items(items=items, repo=repo)
    requested = set(args.items or [])
    if requested:
        return [item for item in ranked if item.id in requested]
    return spec_change_unheld_candidates(
        items=dod_unrefused_candidates(
            items=acceptance_eligible_candidates(
                items=ranked, cwd=repo, workflow_name=args.workflow_name
            ),
            repo=repo,
            workflow_name=args.workflow_name,
        ),
        repo=repo,
        workflow_name=args.workflow_name,
    )

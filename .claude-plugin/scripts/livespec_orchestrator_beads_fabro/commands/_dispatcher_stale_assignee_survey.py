"""Grading one surveyed stale assignee: clear it, or hold it with a named reason.

The attribution holds (`claim-unattributable`, `attribution-pending`,
`owner-elsewhere`) are graded before this is reached, by the same
`attribute_claim` every claim goes through, so this takes only an attributed
stale assignee. What is left of the clause's hold order is graded here, from two
measurements: the factory's answer for the stamped run, and whether a live
process owns the item on this host.

THE GRADING IS THE CLAIM LADDER'S OBSERVATION HALF WITHOUT ITS SUCCEEDED ARM.
`factory-unobservable`, `run-live`, `liveness-unobservable` and `dispatch-live`
read exactly as they do for an `active` claim, and in the same order. A
SUCCEEDED run is not a hold for a stale assignee: the item is not a dispatch
claim, so there is no terminal disposition for a succeeded run to be waiting on,
and its pull request is recovery routing's to measure at the next dispatch.
Neither the forge, the dispatch history nor the failure evidence is read, for
the reason `_dispatcher_stranded_claim_measure` gives about readings no verdict
consults.

`claim-changed` and `effect-unobservable` are discovered by the clearance while
it holds the lock, so they are raised in `_dispatcher_stale_assignee_clear`.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stale_assignee_clear import (
    StaleClearRequest,
    clear_stale_assignee,
    recovered,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    HOLD_DISPATCH_LIVE,
    HOLD_FACTORY_UNOBSERVABLE,
    HOLD_LIVENESS_UNOBSERVABLE,
    HOLD_RUN_LIVE,
    OWNER_LIVE,
    OWNER_UNOBSERVABLE,
    RUN_LIVE,
    RUN_UNOBSERVABLE,
    AttributedClaim,
    run_state_from_inventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_measure import (
    FactoryInventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    observe_owner_liveness,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    HeldClaim,
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "survey_stale_assignee",
]


def survey_stale_assignee(
    *,
    repo: Path,
    journal: JournalFile,
    item: WorkItem,
    attributed: AttributedClaim,
    inventory: FactoryInventory,
    dry_run: bool,
) -> RecoveredClaim | HeldClaim:
    """Clear one attributed stale assignee, project the clearance, or hold it."""
    run_state = run_state_from_inventory(
        surveyed=inventory.surveyed,
        status_kinds=inventory.status_kinds,
        run_id=attributed.run_id,
    )
    owner = observe_owner_liveness(repo=repo, work_item_id=item.id)
    reason = _hold_reason(run_state=run_state, owner=owner)
    if reason is not None:
        stamp = attributed.stamp
        return HeldClaim(
            work_item_id=item.id,
            run_id=attributed.run_id,
            factory_name=inventory.name,
            factory_server_url=inventory.server_url,
            dispatching_host=stamp.dispatching_host,
            hold_reason=reason,
            remedy=None,
        )
    request = StaleClearRequest(
        item=item,
        run_id=attributed.run_id,
        factory_name=inventory.name,
        factory_server_url=inventory.server_url,
        run_state=run_state,
    )
    if dry_run:
        return recovered(request=request, effects=())
    return clear_stale_assignee(repo=repo, journal=journal, request=request)


def _hold_reason(*, run_state: str, owner: str) -> str | None:
    """The first of the clause's graded reasons that applies, or None to clear."""
    if run_state == RUN_UNOBSERVABLE:
        return HOLD_FACTORY_UNOBSERVABLE
    if run_state == RUN_LIVE:
        return HOLD_RUN_LIVE
    if owner == OWNER_UNOBSERVABLE:
        return HOLD_LIVENESS_UNOBSERVABLE
    if owner == OWNER_LIVE:
        return HOLD_DISPATCH_LIVE
    return None

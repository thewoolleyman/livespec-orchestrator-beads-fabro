"""What a dry pass reports for a claim it would recover, with no effect performed."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    AttributedClaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_measure import (
    FactoryInventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["projected_claim"]


def projected_claim(
    *,
    item: WorkItem,
    attributed: AttributedClaim,
    inventory: FactoryInventory,
    action: str,
) -> RecoveredClaim:
    """What a live pass WOULD do to this claim, with no effect performed.

    The item's CURRENT status is reported rather than the status the route
    would land it on: a projection that claimed the destination would read, in
    a `--json` payload, exactly like a live pass that had already written it.
    """
    return RecoveredClaim(
        work_item_id=item.id,
        run_id=attributed.run_id,
        factory_name=inventory.name,
        factory_server_url=inventory.server_url,
        reason=action,
        route=action,
        status=item.status,
        effects_written=(),
    )

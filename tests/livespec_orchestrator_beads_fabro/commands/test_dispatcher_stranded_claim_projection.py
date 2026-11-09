"""A dry pass projects a recovery without performing it.

The projection reports the item's CURRENT status rather than the status the
route would land it on, and names no effect written.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    AttributedClaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_measure import (
    FactoryInventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_projection import (
    projected_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_RUN_ID = "01M58N2ATX8N0000000000000A"
_FACTORY = "petri"
_SERVER = "http://127.0.0.1:32276"


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-projected",
        type="bug",
        status="active",
        title="A claim the dry pass projects",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The slice is verified green by the check suite.",
    )


def test_a_projection_reports_the_current_status_and_writes_no_effect() -> None:
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="host-a",
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )
    projection = projected_claim(
        item=_item(),
        attributed=AttributedClaim(stamp=stamp, run_id=_RUN_ID, factory_name=_FACTORY),
        inventory=FactoryInventory(
            name=_FACTORY,
            server_url=_SERVER,
            fabro_bin="fabro",
            surveyed=True,
            status_kinds={},
        ),
        action="run-absent",
    )
    assert projection == RecoveredClaim(
        work_item_id="bd-ib-projected",
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server_url=_SERVER,
        reason="run-absent",
        route="run-absent",
        status="active",
        effects_written=(),
    )

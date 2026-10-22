"""The plan's first canonically-ranked ready child, read off its own tenant.

Split out of `_plan_resume_advance`, which keeps the DERIVATION — which step the
plan owes next and what obligation that step carries. This answers the narrower
ledger question that derivation asks first, and it is the one half of the advance
that reads the work-item store and the ripeness ranker rather than the plan's own
records.

THE CHILD SET IS THE UNION OF BOTH LINKAGE MECHANISMS, because neither is
complete alone: an explicit `parent-child` edge populates `parent` while the
implicit dotted-id hierarchy does not, so either filter returns a plausible
non-empty set while silently omitting the children linked the other way.

AND IT IS NOT A CARRIER ENUMERATION. A plan's ASSERTIONS are carried by whatever
the epic's carrier-map scope event names, which is routinely an item in a sibling
tenant filed under the cross-tenant execution mirror — and no such item is a
child of this epic by either mechanism. So an empty answer here means the plan
has no ready child, never that the plan has nothing outstanding;
`_plan_carrier_gate` answers the carrier question, and `_plan_resume_advance`
asks both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_child_edges import (
    plan_child_ids_from_dependencies,
    plan_child_ids_from_id_hierarchy,
)
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "next_ready_child_id",
]


def next_ready_child_id(*, config: StoreConfig, epic_id: str) -> str | None:
    """Return this plan's first canonically-ranked ready child, if one exists."""
    records = make_beads_client(config=config).list_issues()
    child_ids = plan_child_ids_from_dependencies(records=records, epic_id=epic_id) | (
        plan_child_ids_from_id_hierarchy(records=records, epic_id=epic_id)
    )
    items = list(
        materialize_work_items(records=read_work_items(path=config.work_items_path)).values()
    )
    ranked_positions = {
        candidate["work_item_ref"]: position
        for position, candidate in enumerate(rank_candidates(items=items))
    }
    ready_children = child_ids & ranked_positions.keys()
    if not ready_children:
        return None
    return min(ready_children, key=ranked_positions.__getitem__)

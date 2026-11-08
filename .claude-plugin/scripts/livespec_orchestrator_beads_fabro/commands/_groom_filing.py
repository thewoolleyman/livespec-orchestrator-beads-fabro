"""The groom front-end's local-slice filing and plan-parent propagation seam.

`groom.file_approved_slices` owns approval, complete-cut planning and closing
the original item. This module owns the lower-level ledger work shared by every
local slice: carrying the original's plan parent into its replacement, filing
through the capture seam and retaining the approval provenance.
"""

from __future__ import annotations

from typing import Any, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import EDGE_PARENT_CHILD, make_beads_client
from livespec_orchestrator_beads_fabro._store_groom_approval import (
    GroomApproval,
    record_groom_approval,
)
from livespec_orchestrator_beads_fabro.commands._groom_types import (
    SliceRouteRefusal,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    ClaimWriteRefused,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["file_local_slice", "plan_parent_id"]


def file_local_slice(
    *,
    path: StoreConfig,
    item: WorkItem,
    approval: GroomApproval,
    size_justification: object,
    plan_parent_id: str | None,
) -> SliceRouteRefusal | None:
    """File one approved local slice, route it and stamp its approval.

    The three writes are kept in one place because they are one act: a slice
    that is filed but not routed is not ready, and a slice that is filed but
    not stamped is a slice nobody can attribute later. A route the claim-token
    protocol refused is answered beside the parse; the slice is stamped all
    the same, because the approval was given whether or not the route landed.
    """
    routed = file_captured_work_item(
        path=path,
        item=item,
        checklist=DefinitionOfReadyChecklist(
            single_coherent_done=True,
            autonomously_verifiable=True,
            autonomy_tiered=True,
            dependency_linked=True,
            repo_targeted=True,
            above_floor=True,
        ),
        size_justification=size_justification,
        plan_parent_id=plan_parent_id,
    )
    failure = None if is_successful(routed) else unsafe_perform_io(routed.failure())
    refused = (
        SliceRouteRefusal(slice_id=item.id, outcome=failure.outcome)
        if isinstance(failure, ClaimWriteRefused)
        else None
    )
    # Stamped AFTER intake routing: the router rewrites the slice's modeled
    # metadata, so a stamp placed before it would be overlaid by the very
    # write that makes the slice ready.
    record_groom_approval(path=path, work_item_id=item.id, approval=approval)
    return refused


def plan_parent_id(*, path: StoreConfig, item_id: str) -> str | None:
    """Read the target's parent-child edge for propagation to every local slice."""
    record = make_beads_client(config=path).show_issue(issue_id=item_id)
    parent_id = record.get("parent_id")
    edges = cast(
        "list[object]",
        record.get("dependencies") if isinstance(record.get("dependencies"), list) else [],
    )
    edge_parent = next(
        (
            cast("dict[str, Any]", edge).get("depends_on_id")
            for edge in edges
            if isinstance(edge, dict)
            and cast("dict[str, Any]", edge).get("type") == EDGE_PARENT_CHILD
        ),
        None,
    )
    return (
        parent_id
        if isinstance(parent_id, str)
        else edge_parent
        if isinstance(edge_parent, str)
        else None
    )

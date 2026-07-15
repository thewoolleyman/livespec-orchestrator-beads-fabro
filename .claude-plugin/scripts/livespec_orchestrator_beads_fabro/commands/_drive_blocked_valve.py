"""Human-valve action for clearing dispatcher-level needs-human blocks."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_blocked_reason
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["unblock_item"]


def unblock_item(
    *, config: StoreConfig, item: WorkItem, action_id: str, target_status: str
) -> dict[str, Any]:
    if item.status != "blocked" or item.blocked_reason != "needs-human":
        return {
            "action_id": action_id,
            "kind": "human-valve",
            "status": "failed",
            "domain_error": "invalid-source-state",
            "summary": "unblock requires a blocked item with blocked_reason needs-human.",
            "work_item_ref": item.id,
        }
    update_work_item_blocked_reason(
        path=config, item_id=item.id, status=target_status, blocked_reason=None
    )
    return {
        "action_id": action_id,
        "kind": "human-valve",
        "work_item_ref": item.id,
        "status": "green",
        "target_status": target_status,
        "journal": {
            "actor": "operator",
            "stage": "human-valve-unblock",
            "work_item_id": item.id,
        },
        "summary": f"Unblocked {item.id}: blocked -> {target_status}; cleared needs-human.",
    }

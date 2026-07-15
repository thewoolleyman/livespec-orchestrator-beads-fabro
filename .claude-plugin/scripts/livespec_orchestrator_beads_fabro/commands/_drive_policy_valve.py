"""Human-valve actions for operator policy-label edits."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["set_policy"]


def set_policy(
    *, config: StoreConfig, item: WorkItem, action_id: str, action: str, value: str
) -> dict[str, Any]:
    store.update_work_item_policy(
        path=config,
        item_id=item.id,
        admission_policy=value if action == "set-admission" else None,
        acceptance_policy=value if action == "set-acceptance" else None,
    )
    return {
        "action_id": action_id,
        "kind": "human-valve",
        "work_item_ref": item.id,
        "status": "green",
        "target_status": item.status,
        "journal": {
            "actor": "operator",
            "stage": f"human-valve-{action}",
            "work_item_id": item.id,
        },
        "summary": (
            f"Updated {item.id}: {action.removeprefix('set-')} policy -> {value}; "
            "status unchanged."
        ),
        "assignee": item.assignee,
    }

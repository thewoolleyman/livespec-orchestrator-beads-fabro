"""Policy and blocked-state human-valve actions for drive."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_blocked_state
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["resolve_blocked_item", "set_policy"]


def resolve_blocked_item(
    *, config: StoreConfig, item: WorkItem, aid: str, target_status: str
) -> dict[str, Any]:
    if item.status != "blocked" or item.blocked_reason != "needs-human":
        return _valve_refusal(
            aid=aid,
            wid=item.id,
            err="invalid-source-state",
            msg="resolve-blocked requires a blocked needs-human item.",
        )
    update_work_item_blocked_state(
        path=config,
        item_id=item.id,
        status=target_status,
        blocked_reason=None,
    )
    return _valve_success(
        aid=aid,
        wid=item.id,
        stage="human-valve-resolve-blocked",
        status=target_status,
        assignee=None,
        msg=f"Resolved {item.id}: blocked -> {target_status}.",
    )


def set_policy(
    *, config: StoreConfig, item: WorkItem, aid: str, action: str, value: str
) -> dict[str, Any]:
    store.update_work_item_policy(
        path=config,
        item_id=item.id,
        admission_policy=value if action == "set-admission" else None,
        acceptance_policy=value if action == "set-acceptance" else None,
    )
    return _valve_success(
        aid=aid,
        wid=item.id,
        stage=f"human-valve-{action}",
        status=item.status,
        assignee=item.assignee,
        msg=(
            f"Updated {item.id}: {action.removeprefix('set-')} policy -> {value}; "
            "status unchanged."
        ),
    )


def _valve_success(
    *, aid: str, wid: str, stage: str, status: str, assignee: str | None, msg: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action_id": aid,
        "kind": "human-valve",
        "work_item_ref": wid,
        "status": "green",
        "target_status": status,
        "journal": {"actor": "operator", "stage": stage, "work_item_id": wid},
        "summary": msg,
    }
    return payload if assignee is None else payload | {"assignee": assignee}


def _valve_refusal(*, aid: str, err: str, msg: str, wid: str) -> dict[str, Any]:
    return {
        "action_id": aid,
        "kind": "human-valve",
        "status": "failed",
        "domain_error": err,
        "summary": msg,
        "work_item_ref": wid,
    }

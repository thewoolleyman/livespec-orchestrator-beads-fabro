"""Shared result-payload helpers for the drive human-valve action modules.

`valve_success` / `valve_refusal` / `invalid_source_state` were duplicated
across `_drive_valves` and `_drive_policy_valves`; hoisting them here gives the
transport and both handler modules one source (and keeps each module under the
file-LLOC ceiling).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["invalid_source_state", "valve_refusal", "valve_success"]


def valve_success(
    *, aid: str, wid: str, stage: str, status: str, assignee: str | None, msg: str
) -> dict[str, Any]:
    """Build a green valve-action payload (with an optional assignee)."""
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


def valve_refusal(*, aid: str, err: str, msg: str, wid: str | None = None) -> dict[str, Any]:
    """Build a failed valve-action payload (with an optional work-item ref)."""
    payload: dict[str, Any] = {
        "action_id": aid,
        "kind": "human-valve",
        "status": "failed",
        "domain_error": err,
        "summary": msg,
    }
    return payload if wid is None else payload | {"work_item_ref": wid}


def invalid_source_state(*, aid: str, item: WorkItem, expected: str) -> dict[str, Any]:
    """Refuse an action whose item is not in the required source status."""
    return valve_refusal(
        aid=aid,
        wid=item.id,
        err="invalid-source-state",
        msg=f"{aid} expected {expected} source state for {item.id}; found {item.status}.",
    )

"""Policy, blocked-state, per-item cap, and queue-control human-valve actions."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._store_cap_mutations import update_work_item_cap
from livespec_orchestrator_beads_fabro._store_mutations import update_work_item_blocked_state
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    ACCEPTANCE_REWORK_CAP_LABEL,
    MERGE_ON_REVIEW_CAP_LABEL,
    REVIEW_FIX_CAP_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    CONFIG_KEYS,
    ConfigKey,
    parse_config_value,
    value_domain,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "CAP_ACTION_VERBS",
    "move_item",
    "resolve_blocked_item",
    "set_cap",
    "set_policy",
]

# Targets an operator may move a selected item to for hands-on queue control.
# `done`, `acceptance`, and `pending-approval` are deliberately excluded: `done`
# is reached only by accepting from `acceptance` (the ship-guard against
# force-shipping unverified work), and `acceptance`/`pending-approval` are
# entered only on their own guarded/entry paths.
_MOVE_ALLOWED: frozenset[str] = frozenset({"backlog", "ready", "blocked", "active"})

# Each per-item cap-override drive verb, mapped to (its `.livespec.jsonc`
# dispatcher setting key, the raw beads-label prefix the Dispatcher resolver
# reads back — see _dispatcher_policy_settings.effective_*_cap). The setting key
# is the single source for the value type used to validate the operator's value.
_CAP_ACTIONS: dict[str, tuple[str, str]] = {
    "set-merge-on-review-cap": ("merge_on_review_cap", MERGE_ON_REVIEW_CAP_LABEL),
    "set-review-fix-cap": ("review_fix_cap", REVIEW_FIX_CAP_LABEL),
    "set-acceptance-rework-cap": ("acceptance_rework_cap", ACCEPTANCE_REWORK_CAP_LABEL),
}
_CAP_CONFIG_KEYS: dict[str, ConfigKey] = {
    action: config_key
    for action, (key_name, _prefix) in _CAP_ACTIONS.items()
    for config_key in CONFIG_KEYS
    if config_key.key == key_name
}
CAP_ACTION_VERBS: frozenset[str] = frozenset(_CAP_ACTIONS)


def resolve_blocked_item(
    *, config: StoreConfig, item: WorkItem, aid: str, target_status: str
) -> dict[str, Any]:
    if item.status != "blocked" or item.blocked_reason != "needs-human":
        return valve_refusal(
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
    return valve_success(
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
    return valve_success(
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


def set_cap(
    *, config: StoreConfig, item: WorkItem, aid: str, action: str, value: str
) -> dict[str, Any]:
    """Set one of the three per-item cap-override labels the resolver reads.

    Mirrors `set_policy` for the caps that carry no `WorkItem` field: the value
    is validated against the setting's declared schema type (a bad value is
    refused with a clear domain error naming the expected domain), then written
    as the raw beads label `<prefix><value>` the Dispatcher resolver reads. The
    write is label-only, so status/assignee are unchanged.
    """
    config_key = _CAP_CONFIG_KEYS[action]
    label_prefix = _CAP_ACTIONS[action][1]
    if parse_config_value(config_key=config_key, raw_value=value) is None:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="invalid-cap-value",
            msg=(
                f"{action} refused: invalid value {value!r} for {config_key.key}; "
                f"expected {value_domain(config_key=config_key)}."
            ),
        )
    update_work_item_cap(path=config, item_id=item.id, label_prefix=label_prefix, value=value)
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=f"human-valve-{action}",
        status=item.status,
        assignee=item.assignee,
        msg=f"Updated {item.id}: {action.removeprefix('set-')} -> {value}; status unchanged.",
    )


def move_item(
    *, config: StoreConfig, item: WorkItem, aid: str, target_status: str
) -> dict[str, Any]:
    """Move a selected item to an operator-movable status for queue control.

    Broad by design (`backlog`/`ready`/`blocked`/`active`) but ship-guarded:
    `done`, `acceptance`, and `pending-approval` are refused with a clear error,
    so no operator can force unverified work to `done` outside the
    accept-from-acceptance path. Writes through the same `update_work_item_status`
    seam the other valves use.
    """
    if target_status not in _MOVE_ALLOWED:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="forbidden-move-target",
            msg=(
                f"move refused: {target_status!r} is not an operator-movable target "
                f"(allowed: {', '.join(sorted(_MOVE_ALLOWED))}). "
                "done is reached only by accepting from acceptance (the ship-guard); "
                "acceptance and pending-approval are entered only on their guarded paths."
            ),
        )
    store.update_work_item_status(path=config, item_id=item.id, status=target_status)
    return valve_success(
        aid=aid,
        wid=item.id,
        stage="human-valve-move",
        status=target_status,
        assignee=None,
        msg=f"Moved {item.id}: {item.status} -> {target_status}.",
    )

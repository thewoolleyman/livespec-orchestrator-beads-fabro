"""Policy, blocked-state, per-item cap, and queue-control human-valve actions."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._store_cap_mutations import update_work_item_cap
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_blocked_state_and_reconcile,
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    ACCEPTANCE_REWORK_CAP_LABEL,
    MERGE_ON_REVIEW_CAP_LABEL,
    REVIEW_FIX_CAP_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._drive_answer import (
    AnswerDelivery,
    answer_note,
    deliver_answer,
)
from livespec_orchestrator_beads_fabro.commands._drive_answer_disposition import (
    answer_press_refusal,
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
    "set_workflow_scope_override",
]

# Targets an operator may move a selected item to for hands-on queue control.
# `done`, `acceptance`, and `pending-approval` are deliberately excluded: `done`
# is reached only by accepting from `acceptance` (the ship-guard against
# force-shipping unverified work), and `acceptance`/`pending-approval` are
# entered only on their own guarded/entry paths.
_MOVE_ALLOWED: frozenset[str] = frozenset({"backlog", "ready", "blocked"})

# Each per-item cap-override drive verb, mapped to (its `.livespec.jsonc`
# dispatcher setting key, the raw beads-label prefix the Dispatcher resolver
# reads back — see _dispatcher_policy_overrides.effective_*_cap). The setting key
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

# The explicit clear-to-inherit sentinel: `set-<cap>:<id>:clear` REMOVES the
# per-item override label so the item reinherits the global default. `clear` can
# never collide with a real cap value (booleans are true/false; the int caps are
# positive integers), and an explicit token is less error-prone than a bare empty
# trailing field. The operator console sends this when its per-item override
# command carries `value: null`.
_CLEAR_SENTINEL = "clear"


def resolve_blocked_item(
    *,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    target_status: str,
    delivery: AnswerDelivery | None = None,
) -> dict[str, Any]:
    """Resolve a blocked needs-human item, carrying the operator's answer if one came.

    `delivery` is the answer to the question the TERMINATED run published
    (`_drive_answer`). ORDER IS LOAD-BEARING: it lands in the ledger BEFORE the
    transition, because a `ready` item is selectable by `next` the instant the
    status write returns — a transition that ran first could be picked up and
    re-dispatched against a brief that still lacked the answer, which is the
    exact miss this route exists to close. Writing first also makes a refused
    answer free: nothing has moved, so the operator rewords and re-runs the
    identical action.

    WHO may answer is graded before WHAT they answered, and both before
    anything is written. `answer_press_refusal` enforces the item's effective
    answer disposition (`_drive_answer_disposition`); it runs first because a
    press the disposition does not admit is refused whatever its text says, so
    grading the text first would only tell an unadmitted presser how to reword
    an answer that was never going to land.
    """
    if item.status != "blocked" or item.blocked_reason != "needs-human":
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="invalid-source-state",
            msg="resolve-blocked requires a blocked needs-human item.",
        )
    if delivery is not None:
        unadmitted = answer_press_refusal(config=config, item=item, aid=aid, delivery=delivery)
        if unadmitted is not None:
            return unadmitted
        refusal = deliver_answer(config=config, item=item, aid=aid, delivery=delivery)
        if refusal is not None:
            return refusal
    write_blocked_state_and_reconcile(
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
        msg=f"Resolved {item.id}: blocked -> {target_status}{answer_note(delivery=delivery)}.",
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


def set_workflow_scope_override(
    *, config: StoreConfig, item: WorkItem, aid: str, value: str
) -> dict[str, Any]:
    if item.status != "ready" or item.factory_safety is not None or not item.awaits_scope_override:
        result = valve_refusal(
            aid=aid,
            wid=item.id,
            err="invalid-source-state",
            msg=(
                "set-workflow-scope-override requires a ready item whose "
                "awaits_scope_override signal is true and factory_safety is null."
            ),
        )
        result["error"] = "invalid-source-state"
        return result
    store.update_work_item_workflow_scope_override(
        path=config,
        item_id=item.id,
        value=value,
    )
    return valve_success(
        aid=aid,
        wid=item.id,
        stage="human-valve-set-workflow-scope-override",
        status=item.status,
        assignee=item.assignee,
        msg=(f"Recorded {item.id}: workflow scope override -> {value}; " "status unchanged."),
    )


def set_cap(
    *, config: StoreConfig, item: WorkItem, aid: str, action: str, value: str
) -> dict[str, Any]:
    """Set OR CLEAR one of the three per-item cap-override labels the resolver reads.

    Mirrors `set_policy` for the caps that carry no `WorkItem` field: a real value
    is validated against the setting's declared schema type (a bad value is
    refused with a clear domain error naming the expected domain), then written as
    the raw beads label `<prefix><value>` the Dispatcher resolver reads. The
    reserved value `clear` (`_CLEAR_SENTINEL`) instead REMOVES the per-item label so
    the item reinherits the global default; clearing an already-absent override is
    a green no-op. The write is label-only, so status/assignee are unchanged.
    """
    config_key = _CAP_CONFIG_KEYS[action]
    label_prefix = _CAP_ACTIONS[action][1]
    if value == _CLEAR_SENTINEL:
        update_work_item_cap(path=config, item_id=item.id, label_prefix=label_prefix, value=None)
        return valve_success(
            aid=aid,
            wid=item.id,
            stage=f"human-valve-{action}",
            status=item.status,
            assignee=item.assignee,
            msg=(
                f"Cleared {action.removeprefix('set-')} override on {item.id}; "
                "inherits global default."
            ),
        )
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

    Broad by design (`backlog`/`ready`/`blocked`) but ship-guarded:
    `done`, `acceptance`, and `pending-approval` are refused with a clear error,
    so no operator can force unverified work to `done` outside the
    accept-from-acceptance path. Writes through the same lifecycle seam the
    other valves use, so the move also reconciles the runs the item disowns.
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
    write_work_item_status_and_reconcile(
        path=config,
        item_id=item.id,
        status=target_status,
        clear_assignee=True,
    )
    return valve_success(
        aid=aid,
        wid=item.id,
        stage="human-valve-move",
        status=target_status,
        assignee=None,
        msg=f"Moved {item.id}: {item.status} -> {target_status}.",
    )

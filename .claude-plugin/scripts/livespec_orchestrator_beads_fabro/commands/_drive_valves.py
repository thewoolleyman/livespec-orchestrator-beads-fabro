"""Action routing, and the ledger-only human valves, for `drive`.

The action-id grammar lives in `_drive_valve_grammar`, the `reject` valve in
`_drive_reject_valve`, the merge-hold valve in `_drive_merge_hold_valve`, the
factory-safety valve in `_drive_factory_safety_valve`, and the policy / cap /
queue / blocked-state valves in `_drive_policy_valves`; what stays here is the
router that dispatches on a parsed action, and the two valves that do nothing
but write the ledger.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    ungradeable_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    InvokerIdentity,
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._drive_answer import answer_delivery
from livespec_orchestrator_beads_fabro.commands._drive_factory_safety_valve import (
    set_factory_safety,
)
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_valve import set_merge_hold
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import (
    CAP_ACTION_VERBS,
    move_item,
    resolve_blocked_item,
    set_cap,
    set_policy,
    set_workflow_scope_override,
)
from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import (
    HumanValveRunner,
    journal_rework_return,
    reject_item,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_grammar import (
    parse_human_valve_action,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_predicates import can_approve_item
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["run_human_valve_action"]


def run_human_valve_action(
    *,
    repo: Path,
    action_id: str,
    runner: HumanValveRunner | None = None,
    identity: InvokerIdentity | None = None,
    answer: str | None = None,
) -> dict[str, Any]:
    """Run one human-valve action, attributing whatever it journals.

    `identity` is the invocation's resolved invoker; `None` means "resolve it
    from the environment here", so a direct caller is still attributed rather
    than unattributed.

    `answer` is the operator's answer to the question a terminated run
    published, consumed only by `resolve-blocked` (`_drive_answer`); the
    transport neither reads nor validates it, because the layer that knows what
    an unusable answer is, is the one that knows where it will be written.
    """
    resolved_identity = default_invoker_identity() if identity is None else identity
    parsed = parse_human_valve_action(action_id=action_id)
    if parsed is None:
        return valve_refusal(
            aid=action_id,
            err="invalid-action-id",
            msg="Unsupported human valve action id.",
        )
    action, item_id, action_value = parsed
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    item = _find_item(items=list(store.read_work_items(path=config)), item_id=item_id)
    if item is None:
        return valve_refusal(
            aid=action_id,
            err="work-item-not-found",
            msg=f"work-item not found: {item_id}",
        )
    return _route(
        call=_ValveCall(
            repo=repo,
            config=config,
            item=item,
            action=action,
            action_id=action_id,
            value=cast("str", action_value),
            runner=runner,
            identity=resolved_identity,
        ),
        answer=answer,
    )


@dataclass(frozen=True, kw_only=True)
class _ValveCall:
    """One PARSED valve invocation: the verb, the item it named, and its inputs.

    Assembled once by the supervisor above so the routing below is a pure
    dispatch on `action`. The alternative — threading nine independent
    arguments through each routing layer — is what pushed this router past the
    branch ceiling in the first place.
    """

    repo: Path
    config: StoreConfig
    item: WorkItem
    action: str
    action_id: str
    value: str
    runner: HumanValveRunner | None
    identity: InvokerIdentity


def _route(*, call: _ValveCall, answer: str | None) -> dict[str, Any]:
    """Dispatch one parsed action onto its valve."""
    edit = _policy_edit(call=call)
    if edit is not None:
        return edit
    if call.action == "resolve-blocked":
        return resolve_blocked_item(
            config=call.config,
            item=call.item,
            aid=call.action_id,
            target_status=call.value,
            delivery=answer_delivery(answer=answer, identity=call.identity, repo=call.repo),
        )
    if call.action == "approve":
        return _approve_item(
            repo=call.repo, config=call.config, item=call.item, action_id=call.action_id
        )
    if call.action == "accept":
        return _accept_item(config=call.config, item=call.item, action_id=call.action_id)
    if call.action == "move":
        return move_item(
            config=call.config, item=call.item, aid=call.action_id, target_status=call.value
        )
    result = reject_item(
        repo=call.repo,
        config=call.config,
        item=call.item,
        aid=call.action_id,
        reject_kind=call.value,
        runner=call.runner,
    )
    journal_rework_return(
        repo=call.repo, identity=call.identity, reject_kind=call.value, result=result
    )
    return result


def _policy_edit(*, call: _ValveCall) -> dict[str, Any] | None:
    """The valves that write ONE field of an item and never its status, or `None`.

    Grouped because the contract groups them: a policy edit, the workflow-scope
    assertion, the factory-safety record, a cap override and the merge hold each
    modify only the named field and MUST NOT move the item. The merge hold is the
    one member that also reaches the forge, which is why it alone is handed the
    command runner; the factory-safety record is the one member that asserts no
    source state at all, because its axis is orthogonal to the lifecycle.
    """
    if call.action == "set-factory-safety":
        return set_factory_safety(
            config=call.config, item=call.item, aid=call.action_id, value=call.value
        )
    if call.action in {"set-admission", "set-acceptance"}:
        return set_policy(
            config=call.config,
            item=call.item,
            aid=call.action_id,
            action=call.action,
            value=call.value,
        )
    if call.action == "set-workflow-scope-override":
        return set_workflow_scope_override(
            config=call.config, item=call.item, aid=call.action_id, value=call.value
        )
    if call.action in CAP_ACTION_VERBS:
        return set_cap(
            config=call.config,
            item=call.item,
            aid=call.action_id,
            action=call.action,
            value=call.value,
        )
    if call.action == "set-merge-hold":
        return set_merge_hold(
            repo=call.repo,
            config=call.config,
            item=call.item,
            aid=call.action_id,
            value=call.value,
            runner=call.runner,
        )
    return None


def _find_item(*, items: list[WorkItem], item_id: str) -> WorkItem | None:
    return next((item for item in items if item.id == item_id), None)


def _approve_item(
    *, repo: Path, config: StoreConfig, item: WorkItem, action_id: str
) -> dict[str, Any]:
    if item.status != "pending-approval":
        return invalid_source_state(aid=action_id, item=item, expected="pending-approval")
    if not can_approve_item(item=item, cwd=repo):
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="invalid-source-state",
            msg="approve requires an effective-manual pending-approval item.",
        )
    # The entry-to-`ready` wall (the effective-acceptance-criteria clause of contracts.md).
    # The refusal writes NOTHING: the item rests at `pending-approval` rather
    # than being routed to `backlog` or `blocked` on these grounds.
    ungradeable = ungradeable_criteria_refusal(item=item, cwd=repo)
    if ungradeable is not None:
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="ungradeable-acceptance-criteria",
            msg=f"approve refused: {ungradeable}.",
        )
    store.update_work_item_status(path=config, item_id=item.id, status="ready")
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-approve",
        status="ready",
        assignee=None,
        msg=f"Approved {item.id}: pending-approval -> ready.",
    )


def _accept_item(*, config: StoreConfig, item: WorkItem, action_id: str) -> dict[str, Any]:
    if item.status != "acceptance":
        return invalid_source_state(aid=action_id, item=item, expected="acceptance")
    write_work_item_status_and_reconcile(path=config, item_id=item.id, status="done")
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-accept",
        status="done",
        assignee=None,
        msg=f"Accepted {item.id}: acceptance -> done.",
    )

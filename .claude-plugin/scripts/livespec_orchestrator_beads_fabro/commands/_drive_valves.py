"""Routing, and the entry-to-`ready` valve, for `drive`.

The `reject` valve lives in `_drive_reject_valve`, the `accept` valve in
`_drive_accept_valve`, the merge-hold valve in `_drive_merge_hold_valve`, the
policy / cap / queue / blocked-state valves in `_drive_policy_valves`, the
`approve` valve in `_drive_approve_valve`, and the action-id grammar the router
dispatches on in `_drive_valve_grammar`; what stays here is that router.

`approve` moved to `_drive_approve_valve` once the pre-admission
Definition-of-Done judgement gave it a model call, for the same reason `accept`
moved out when the human-attested leg gave it a forge read: a module whose whole
job is routing must not also be the one that reaches a provider or a forge.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    InvokerIdentity,
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import accept_item
from livespec_orchestrator_beads_fabro.commands._drive_answer import answer_delivery
from livespec_orchestrator_beads_fabro.commands._drive_approve_valve import approve_item
from livespec_orchestrator_beads_fabro.commands._drive_factory_safety_valve import (
    FACTORY_SAFETY_ACTION,
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
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal
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
        return approve_item(
            repo=call.repo, config=call.config, item=call.item, action_id=call.action_id
        )
    if call.action == "accept":
        return accept_item(
            repo=call.repo, config=call.config, item=call.item, action_id=call.action_id
        )
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
    assertion, the factory-safety opt-out, a cap override and the merge hold each
    modify only the named field and MUST NOT move the item. The merge hold is the
    one member that also reaches the forge, which is why it alone is handed the
    command runner; the factory-safety opt-out is the one that also journals,
    which is why it alone is handed the repo path and the identity.
    """
    if call.action == FACTORY_SAFETY_ACTION:
        return set_factory_safety(
            repo=call.repo,
            config=call.config,
            item=call.item,
            aid=call.action_id,
            value=call.value,
            identity=call.identity,
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

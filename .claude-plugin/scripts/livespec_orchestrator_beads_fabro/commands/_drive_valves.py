"""Human-valve actions for the drive operator surface."""

from collections.abc import Callable
from pathlib import Path
from subprocess import run
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import effective_admission_policy
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import (
    resolve_blocked_item,
    set_policy,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["is_human_valve_action", "run_human_valve_action"]


class HumanValveCommandRun(Protocol):
    @property
    def returncode(self) -> int: ...

    @property
    def stderr(self) -> str: ...


HumanValveRunner = Callable[..., object]


def run_human_valve_action(
    *, repo: Path, action_id: str, runner: HumanValveRunner | None = None
) -> dict[str, Any]:
    parsed = _parse_human_valve_action(action_id=action_id)
    if parsed is None:
        return _valve_refusal(
            aid=action_id,
            err="invalid-action-id",
            msg="Unsupported human valve action id.",
        )
    action, item_id, action_value = parsed
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    item = _find_item(items=list(store.read_work_items(path=config)), item_id=item_id)
    if item is None:
        return _valve_refusal(
            aid=action_id,
            err="work-item-not-found",
            msg=f"work-item not found: {item_id}",
        )
    if action == "resolve-blocked":
        return resolve_blocked_item(
            config=config,
            item=item,
            aid=action_id,
            target_status=cast("str", action_value),
        )
    if action in {"approve", "accept"}:
        valve_action = _approve_item if action == "approve" else _accept_item
        return valve_action(config=config, item=item, action_id=action_id)
    if action in {"set-admission", "set-acceptance"}:
        return set_policy(
            config=config,
            item=item,
            aid=action_id,
            action=action,
            value=cast("str", action_value),
        )
    return _reject_item(
        repo=repo,
        config=config,
        item=item,
        aid=action_id,
        reject_kind=cast("str", action_value),
        runner=runner,
    )


def is_human_valve_action(*, action_id: str) -> bool:
    return action_id.startswith(
        (
            "approve:",
            "accept:",
            "reject:",
            "resolve-blocked:",
            "set-admission:",
            "set-acceptance:",
        )
    )


def _parse_human_valve_action(*, action_id: str) -> tuple[str, str, str | None] | None:
    match action_id.split(":"):
        case [("approve" | "accept") as action, item] if item != "":
            return (action, item, None)
        case ["reject", item, ("rework" | "regroom") as value] if item != "":
            return ("reject", item, value)
        case ["resolve-blocked", item, ("ready" | "backlog") as value] if item != "":
            return ("resolve-blocked", item, value)
        case ["set-admission", item, ("auto" | "manual") as value] if item != "":
            return ("set-admission", item, value)
        case [
            "set-acceptance",
            item,
            ("ai-only" | "human-only" | "ai-then-human") as value,
        ] if item != "":
            return ("set-acceptance", item, value)
        case _:
            return None


def _find_item(*, items: list[WorkItem], item_id: str) -> WorkItem | None:
    return next((item for item in items if item.id == item_id), None)


def _approve_item(*, config: StoreConfig, item: WorkItem, action_id: str) -> dict[str, Any]:
    if item.status != "pending-approval":
        return _invalid_source_state(aid=action_id, item=item, expected="pending-approval")
    if effective_admission_policy(item=item) != "manual":
        return _valve_refusal(
            aid=action_id,
            wid=item.id,
            err="invalid-source-state",
            msg="approve requires an effective-manual pending-approval item.",
        )
    store.update_work_item_status(path=config, item_id=item.id, status="ready")
    return _valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-approve",
        status="ready",
        assignee=None,
        msg=f"Approved {item.id}: pending-approval -> ready.",
    )


def _accept_item(*, config: StoreConfig, item: WorkItem, action_id: str) -> dict[str, Any]:
    if item.status != "acceptance":
        return _invalid_source_state(aid=action_id, item=item, expected="acceptance")
    store.update_work_item_status(path=config, item_id=item.id, status="done")
    return _valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-accept",
        status="done",
        assignee=None,
        msg=f"Accepted {item.id}: acceptance -> done.",
    )


def _reject_item(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    reject_kind: str,
    runner: HumanValveRunner | None,
) -> dict[str, Any]:
    if item.status != "acceptance":
        return _invalid_source_state(aid=aid, item=item, expected="acceptance")
    target_status = "active" if reject_kind == "rework" else "backlog"
    if reject_kind == "regroom":
        refusal = _revert_merged_change(repo=repo, item=item, aid=aid, runner=runner)
        if refusal is not None:
            return refusal
    store.update_work_item_status(path=config, item_id=item.id, status=target_status)
    return _valve_success(
        aid=aid,
        wid=item.id,
        stage=f"human-valve-reject-{reject_kind}",
        status=target_status,
        assignee=None,
        msg=f"Rejected {item.id}: acceptance -> {target_status}.",
    )


def _revert_merged_change(
    *, repo: Path, item: WorkItem, aid: str, runner: HumanValveRunner | None
) -> dict[str, Any] | None:
    merge_sha = item.audit.merge_sha if item.audit is not None else None
    if not merge_sha:
        return _valve_refusal(
            aid=aid,
            wid=item.id,
            err="missing-merge-evidence",
            msg="reject:regroom refused: no merged change recorded to revert.",
        )
    argv = ("git", "revert", "--no-edit", merge_sha)
    if runner is None:
        result = run(argv, check=False, cwd=repo, text=True, capture_output=True)  # noqa: S603
    else:
        result = cast("HumanValveCommandRun", runner(argv=argv, cwd=repo))
    if result.returncode == 0:
        return None
    return _valve_refusal(
        aid=aid,
        wid=item.id,
        err="revert-failed",
        msg=f"reject:regroom refused: git revert {merge_sha} failed: {result.stderr}",
    )


def _invalid_source_state(*, aid: str, item: WorkItem, expected: str) -> dict[str, Any]:
    return _valve_refusal(
        aid=aid,
        wid=item.id,
        err="invalid-source-state",
        msg=(f"{aid} expected {expected} source state for {item.id}; found {item.status}."),
    )


def _valve_success(
    *, aid: str, wid: str, stage: str, status: str, assignee: str | None, msg: str
) -> dict[str, Any]:
    payload: dict[str, Any] = dict(
        action_id=aid,
        kind="human-valve",
        work_item_ref=wid,
        status="green",
        target_status=status,
        journal={"actor": "operator", "stage": stage, "work_item_id": wid},
        summary=msg,
    )
    return payload if assignee is None else payload | {"assignee": assignee}


def _valve_refusal(*, aid: str, err: str, msg: str, wid: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = dict(
        action_id=aid, kind="human-valve", status="failed", domain_error=err, summary=msg
    )
    return payload if wid is None else payload | {"work_item_ref": wid}

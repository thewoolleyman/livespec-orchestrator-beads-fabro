"""Work-item derived attention lanes for needs-attention."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.needs_attention import ImplNextOutput, WorkItemHumanValveLane
from livespec_runtime.work_items.lifecycle import lane_of

from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    drive_command,
    host_only_command,
)
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_only_items",
    "human_valves",
    "impl_next",
]

_HOST_ONLY_REFUSAL_STAGE = "host-only-refused"
_RECORDED_REFUSAL_REASON = "recorded-refusal"
_DISPATCHER_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def impl_next(
    *,
    project_root: Path,
    items: list[WorkItem],
    manifest: CrossRepoManifest,
) -> ImplNextOutput | None:
    ranked = rank_candidates(
        items=[item for item in items if item.factory_safety is None],
        manifest=manifest,
    )
    if not ranked:
        return None
    candidate = ranked[0]
    work_item = str(candidate["work_item_ref"])
    return ImplNextOutput(
        work_item=work_item,
        summary=str(candidate["reason"]),
        command=drive_command(project_root=project_root, action_id=f"impl:{work_item}"),
        urgency="medium",
    )


def human_valves(
    *,
    project_root: Path,
    items: list[WorkItem],
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
) -> list[WorkItemHumanValveLane]:
    lanes: list[WorkItemHumanValveLane] = []
    for item in items:
        item_id = item.id
        title = item.title
        status = item.status
        lane_reason = lane_of(item=item, index=index, manifest=manifest).reason
        if status == "pending-approval":
            lanes.append(
                _valve(
                    verb="approve",
                    work_item=item_id,
                    summary=f"Approve pending work-item {item_id}: {title}",
                    project_root=project_root,
                    action_id=f"approve:{item_id}",
                )
            )
        elif status == "acceptance":
            lanes.append(
                _valve(
                    verb="accept",
                    work_item=item_id,
                    summary=f"Accept completed work-item {item_id}: {title}",
                    project_root=project_root,
                    action_id=f"accept:{item_id}",
                )
            )
        elif status == "blocked" and lane_reason == "needs-human":
            lanes.append(
                _valve(
                    verb="resolve-blocked",
                    work_item=item_id,
                    summary=f"Resolve human-needed block for work-item {item_id}: {title}",
                    project_root=project_root,
                    action_id=f"resolve-blocked:{item_id}:ready",
                )
            )
    return lanes


def host_only_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    reasons = _host_only_reasons(project_root=project_root, items=items)
    return [
        _host_only_item(project_root=project_root, repo=repo, work_item=item_id, reason=reason)
        for item_id, reason in reasons.items()
    ]


def _host_only_reasons(*, project_root: Path, items: list[WorkItem]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for item in items:
        if item.status != "done" and item.factory_safety is not None:
            reasons[item.id] = item.factory_safety
    for item_id in _recorded_host_only_refusals(project_root=project_root):
        if item_id not in reasons:
            reasons[item_id] = _RECORDED_REFUSAL_REASON
    return reasons


def _recorded_host_only_refusals(*, project_root: Path) -> tuple[str, ...]:
    journal = project_root / _DISPATCHER_JOURNAL_PATH
    if not journal.is_file():
        return ()
    loaded = attempt(action=lambda: journal.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(loaded, AttemptFailure):
        return ()
    item_ids: list[str] = []
    for line in loaded.splitlines():
        item_id = _host_only_refusal_item_id(line=line)
        if item_id is not None:
            item_ids.append(item_id)
    return tuple(dict.fromkeys(item_ids))


def _host_only_refusal_item_id(*, line: str) -> str | None:
    parsed = attempt(action=lambda: json.loads(line), exceptions=(json.JSONDecodeError,))
    loaded = cast("object", parsed)
    if isinstance(loaded, AttemptFailure) or not isinstance(loaded, dict):
        return None
    record = cast("dict[str, Any]", loaded)
    if record.get("stage") != "outcome":
        return None
    outcome = record.get("outcome")
    if not isinstance(outcome, dict):
        return None
    outcome_record = cast("dict[str, Any]", outcome)
    if outcome_record.get("stage") != _HOST_ONLY_REFUSAL_STAGE:
        return None
    item_id = outcome_record.get("work_item_id")
    return item_id if isinstance(item_id, str) else None


def _host_only_item(
    *,
    project_root: Path,
    repo: str,
    work_item: str,
    reason: str,
) -> AttentionItem:
    return AttentionItem(
        id=f"host-only:{reason}:{work_item}",
        kind="host-only",
        urgency="high",
        summary=f"Host-route work-item {work_item}: factory_safety {reason}.",
        source_ref=SourceRef(repo=repo, work_item=work_item),
        handoff=Handoff(
            kind="shell",
            command=host_only_command(project_root=project_root, work_item=work_item),
        ),
    )


def _valve(
    *,
    verb: str,
    work_item: str,
    summary: str,
    project_root: Path,
    action_id: str,
) -> WorkItemHumanValveLane:
    return WorkItemHumanValveLane(
        verb=verb,
        work_item=work_item,
        summary=summary,
        action_id=action_id,
        command=drive_command(project_root=project_root, action_id=action_id),
    )

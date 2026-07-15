"""Work-item derived attention lanes for needs-attention."""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.needs_attention import ImplNextOutput, WorkItemHumanValveLane
from livespec_runtime.work_items.lifecycle import lane_of

from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import drive_command
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "human_valves",
    "impl_next",
]


def impl_next(
    *,
    project_root: Path,
    items: list[WorkItem],
    manifest: CrossRepoManifest,
) -> ImplNextOutput | None:
    ranked = rank_candidates(items=items, manifest=manifest)
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

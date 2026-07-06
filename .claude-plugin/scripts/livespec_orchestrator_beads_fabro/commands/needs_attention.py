"""Thin needs-attention binding over this plugin's gather primitives."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import asdict
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.hygiene_scan import scan_hygiene
from livespec_runtime.needs_attention import (
    ImplNextOutput,
    PlanThreadOutput,
    SpecNextOutput,
    WorkItemHumanValveLane,
    compose_needs_attention,
)
from livespec_runtime.work_items.lifecycle import lane_of

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands.list_plan_threads import list_plan_threads
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "build_attention",
    "main",
    "render_json",
    "render_markdown",
]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="needs-attention")
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--work-items-path", dest="work_items_path", default=None)
    _ = parser.add_argument("--repo-name", dest="repo_name", default=None)
    _ = parser.add_argument("--skip-hygiene", dest="skip_hygiene", action="store_true")
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    repo_name = args.repo_name if args.repo_name is not None else project_root.name
    attention = build_attention(
        project_root=project_root,
        repo_name=repo_name,
        work_items_path=args.work_items_path,
        include_hygiene=not args.skip_hygiene,
    )
    if args.as_json:
        _ = sys.stdout.write(render_json(attention=attention))
    else:
        _ = sys.stdout.write(render_markdown(attention=attention))
    return 0


def build_attention(
    *,
    project_root: Path,
    repo_name: str,
    work_items_path: str | None = None,
    include_hygiene: bool = True,
) -> list[AttentionItem]:
    items = _load_work_items(project_root=project_root, work_items_path=work_items_path)
    manifest = load_manifest(project_root=project_root)
    materialized = list(materialize_work_items(records=iter(items)).values())
    index = {item.id: item for item in materialized}
    hygiene_scan = (
        scan_hygiene(repo_path=project_root, repo_name=repo_name) if include_hygiene else []
    )
    return (
        compose_needs_attention(
            repo=repo_name,
            spec_next=_spec_next(project_root=project_root),
            impl_next=_impl_next(project_root=project_root, items=materialized, manifest=manifest),
            human_valve_lanes=_human_valves(
                project_root=project_root,
                items=materialized,
                index=index,
                manifest=manifest,
            ),
            plan_threads=_plan_threads(project_root=project_root),
            hygiene_scan=(),
        )
        + hygiene_scan
    )


def render_json(*, attention: list[AttentionItem]) -> str:
    return (
        json.dumps({"attention": [asdict(item) for item in attention]}, indent=2, sort_keys=True)
        + "\n"
    )


def render_markdown(*, attention: list[AttentionItem]) -> str:
    if not attention:
        return "No attention items.\n"
    lines = ["# Needs Attention", ""]
    for item in attention:
        lines.extend(
            [
                f"- `{item.id}` [{item.urgency}] {item.summary}",
                f"  - Handoff: `{item.handoff.command}`",
            ]
        )
    return "\n".join(lines) + "\n"


def _load_work_items(*, project_root: Path, work_items_path: str | None) -> list[WorkItem]:
    config = resolve_store_config(cwd=project_root, work_items_arg=work_items_path)
    return list(read_work_items(path=config.work_items_path))


def _spec_next(*, project_root: Path) -> SpecNextOutput:
    command = f"codex exec livespec:next --json --project-root {_quote(project_root)}"
    return SpecNextOutput(
        op="next",
        spec_target="SPECIFICATION",
        summary="Run the spec-side next primitive.",
        command=command,
    )


def _impl_next(
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
        command=_drive_command(project_root=project_root, action_id=f"impl:{work_item}"),
        urgency="medium",
    )


def _human_valves(
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
                    verb="set-admission",
                    work_item=item_id,
                    summary=f"Resolve human-needed block for work-item {item_id}: {title}",
                    project_root=project_root,
                    action_id=f"set-admission:{item_id}:manual",
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
        command=_drive_command(project_root=project_root, action_id=action_id),
    )


def _plan_threads(*, project_root: Path) -> list[PlanThreadOutput]:
    return [
        PlanThreadOutput(
            topic=topic,
            path=f"plan/{topic}/",
            summary=f"Review plan thread {topic}.",
            command=(
                f"codex exec {_PLUGIN_NAME}:plan "
                f"--project-root {_quote(project_root)} {shlex.quote(topic)}"
            ),
        )
        for topic in list_plan_threads(project_root=project_root)
    ]


def _drive_command(*, project_root: Path, action_id: str) -> str:
    return (
        f"python3 {_quote(_wrapper_path(name='drive.py'))} "
        f"--repo {_quote(project_root)} --action {shlex.quote(action_id)} --json"
    )


def _wrapper_path(*, name: str) -> Path:
    return Path(__file__).parents[2] / "bin" / name


def _quote(path: Path) -> str:
    return shlex.quote(str(path))

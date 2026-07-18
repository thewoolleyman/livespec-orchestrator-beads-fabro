"""Handoff command rendering for needs-attention outputs."""

from __future__ import annotations

import shlex
from pathlib import Path

from livespec_runtime.needs_attention import PlanThreadOutput

from livespec_orchestrator_beads_fabro.commands.list_plan_threads import list_plan_threads

__all__: list[str] = [
    "drive_command",
    "host_only_command",
    "plan_threads",
]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"


def plan_threads(*, project_root: Path) -> list[PlanThreadOutput]:
    return [
        PlanThreadOutput(
            topic=topic,
            path=f"plan/{topic}/",
            summary=f"Review plan thread {topic}.",
            command=(
                f"codex exec {_PLUGIN_NAME}:plan "
                f"--project-root {_quote(path=project_root)} {shlex.quote(topic)}"
            ),
        )
        for topic in list_plan_threads(project_root=project_root)
    ]


def drive_command(*, project_root: Path, action_id: str) -> str:
    return (
        f"python3 {_quote(path=_wrapper_path(name='drive.py'))} "
        f"--repo {_quote(path=project_root)} --action {shlex.quote(action_id)} --json"
    )


def host_only_command(*, project_root: Path, work_item: str) -> str:
    prompt = (
        f"Host-route work-item {work_item} from repository {project_root}. "
        "Run it on the host with required credentials; do not dispatch it to Fabro."
    )
    return f"cd {_quote(path=project_root)} && codex exec {shlex.quote(prompt)} < /dev/null"


def _wrapper_path(*, name: str) -> Path:
    return Path(__file__).parents[2] / "bin" / name


def _quote(*, path: Path) -> str:
    return shlex.quote(str(path))

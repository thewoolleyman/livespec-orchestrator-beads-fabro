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
    "untriaged_backlog_command",
    "untriaged_backlog_summary_command",
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


def untriaged_backlog_command(*, project_root: Path, work_item: str) -> str:
    """Hand off ONE backlog work-item the intake gate never saw."""
    prompt = (
        f"Triage backlog work-item {work_item} in repository {project_root}. "
        "It was filed without running the intake Definition-of-Ready checklist, "
        "so it carries no intake:triaged label and no surface reports it. Run the "
        "checklist over it and route it to its lifecycle state; if it is "
        "deliberately parked, label it intake:triaged to dismiss it from this lane."
    )
    return f"cd {_quote(path=project_root)} && codex exec {shlex.quote(prompt)} < /dev/null"


def untriaged_backlog_summary_command(*, project_root: Path) -> str:
    """Hand off the lower-priority remainder as ONE item, never one per record.

    The remainder is reported in aggregate on purpose: a repository can carry
    hundreds of un-triaged backlog items, and one attention item per record
    would produce noise rather than signal — an attention list nobody reads
    is worse than none.
    """
    prompt = (
        f"Triage the un-triaged backlog work-items in repository {project_root} — "
        "every item in backlog status without the intake:triaged label. Run the "
        "intake Definition-of-Ready checklist over each and route it to its "
        "lifecycle state; label the deliberately-parked ones intake:triaged."
    )
    return f"cd {_quote(path=project_root)} && codex exec {shlex.quote(prompt)} < /dev/null"


def _wrapper_path(*, name: str) -> Path:
    return Path(__file__).parents[2] / "bin" / name


def _quote(*, path: Path) -> str:
    return shlex.quote(str(path))

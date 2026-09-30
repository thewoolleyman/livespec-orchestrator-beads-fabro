"""Handoff command rendering for needs-attention outputs."""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from livespec_runtime.needs_attention import PlanThreadOutput

from livespec_orchestrator_beads_fabro.commands._plan_anchor import (
    PLAN_HINT_PREFIX,
    is_plan_anchor,
)
from livespec_orchestrator_beads_fabro.commands.list_plans import list_plans
from livespec_orchestrator_beads_fabro.commands.plan import handoff_timeline_findings, read_timeline
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "dispatcher_loop_command",
    "drive_command",
    "fabro_events_command",
    "host_only_command",
    "model_fallback_journal_command",
    "plans",
    "pr_view_command",
    "reconcile_merged_command",
    "reconcile_runs_command",
    "release_to_ready_command",
    "untriaged_backlog_command",
    "untriaged_backlog_summary_command",
]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"

_DISPATCH_JOURNAL_SUBPATH = "tmp/fabro-dispatch-journal.jsonl"


@dataclass(frozen=True, slots=True, kw_only=True)
class _PlanTopic:
    slug: str
    epic_id: str | None


def plans(
    *,
    project_root: Path,
    config: StoreConfig,
    items: Iterable[WorkItem],
) -> list[PlanThreadOutput]:
    return [
        _plan_thread_output(project_root=project_root, topic=topic, findings=findings)
        for topic in _plan_topics(project_root=project_root, items=items)
        for findings in (_timeline_findings(config=config, epic_id=topic.epic_id),)
    ]


def _plan_topics(
    *,
    project_root: Path,
    items: Iterable[WorkItem],
) -> list[_PlanTopic]:
    by_slug = {
        topic: _PlanTopic(slug=topic, epic_id=None)
        for topic in list_plans(project_root=project_root)
    }
    by_slug.update({topic.slug: topic for topic in _ledger_plan_topics(items=items)})
    return [by_slug[slug] for slug in sorted(by_slug)]


def _ledger_plan_topics(*, items: Iterable[WorkItem]) -> list[_PlanTopic]:
    topics: list[_PlanTopic] = []
    for item in items:
        topic = _plan_topic(item=item)
        if topic is None:
            continue
        topics.append(_PlanTopic(slug=topic, epic_id=item.id))
    return topics


def _plan_topic(*, item: WorkItem) -> str | None:
    hint = item.spec_commitment_hint
    if item.type != "epic" or item.status == "done" or hint is None:
        return None
    if not is_plan_anchor(spec_id=hint):
        return None
    topic = hint.removeprefix(PLAN_HINT_PREFIX)
    if topic == "":
        return None
    return topic


def _timeline_findings(*, config: StoreConfig, epic_id: str | None) -> tuple[str, ...]:
    if epic_id is None:
        return ()
    return handoff_timeline_findings(entries=read_timeline(config=config, epic_id=epic_id))


def _plan_thread_output(
    *,
    project_root: Path,
    topic: _PlanTopic,
    findings: tuple[str, ...],
) -> PlanThreadOutput:
    if not findings:
        return PlanThreadOutput(
            topic=topic.slug,
            path=f"plan/{topic.slug}/",
            summary=f"Review plan {topic.slug}.",
            command=_plan_command(project_root=project_root, topic=topic.slug),
        )
    return PlanThreadOutput(
        topic=topic.slug,
        path=f"plan/{topic.slug}/",
        summary=f"Repair plan {topic.slug} handoff: {findings[0]}.",
        command=_plan_command(project_root=project_root, topic=topic.slug),
        urgency="high",
    )


def _plan_command(*, project_root: Path, topic: str) -> str:
    return (
        f"codex exec {_PLUGIN_NAME}:plan "
        f"--project-root {_quote(path=project_root)} {shlex.quote(topic)}"
    )


def drive_command(*, project_root: Path, action_id: str) -> str:
    return (
        f"python3 {_quote(path=_wrapper_path(name='drive.py'))} "
        f"--repo {_quote(path=project_root)} --action {shlex.quote(action_id)} --json"
    )


def dispatcher_loop_command(*, project_root: Path) -> str:
    return (
        f"python3 {_quote(path=_wrapper_path(name='dispatcher.py'))} "
        f"loop --repo {_quote(path=project_root)} --budget 1 --parallel 1 --json"
    )


def host_only_command(*, project_root: Path, work_item: str) -> str:
    prompt = (
        f"Host-route work-item {work_item} from repository {project_root}. "
        "Run it on the host with required credentials; do not dispatch it to Fabro."
    )
    return f"cd {_quote(path=project_root)} && codex exec {shlex.quote(prompt)} < /dev/null"


def reconcile_merged_command(*, project_root: Path, work_item: str) -> str:
    return (
        f"python3 {_quote(path=_wrapper_path(name='dispatcher.py'))} "
        f"reconcile-merged --repo {_quote(path=project_root)} "
        f"--item {shlex.quote(work_item)} --json"
    )


def reconcile_runs_command(*, project_root: Path, factory: str) -> str:
    """The exact remedy for ONE factory's orphaned runs.

    Narrowed with `--factory` rather than handing over the whole-inventory
    form: the lane reports per run, so the remedy beside a run must act on the
    factory that run is holding a slot on and not silently sweep the others.
    """
    return (
        f"python3 {_quote(path=_wrapper_path(name='dispatcher.py'))} "
        f"reconcile-runs --repo {_quote(path=project_root)} "
        f"--factory {shlex.quote(factory)} --json"
    )


def fabro_events_command(*, fabro_bin: str, run_id: str, server_url: str) -> str:
    """The SERVER-QUALIFIED events read, spelled exactly as the port spells it.

    `SPECIFICATION/contracts.md` section "Factory-configurable ACP
    fallback priority" requires the projection-failure fact to carry "a
    `shell` handoff containing the same executable server-qualified
    inspection command reconciliation uses", so the argv below mirrors
    `FabroPort.events` term for term -- including `--server` AFTER the
    subcommand, which the pinned 0.254.0 CLI requires and a top-level
    `--server` hard-errors on. A handoff an operator pastes and watches
    fail is worse than none: it reads as the factory being broken when
    the command was.
    """
    return (
        f"{shlex.quote(fabro_bin)} events {shlex.quote(run_id)} "
        f"--json --server {shlex.quote(server_url)}"
    )


def model_fallback_journal_command(*, project_root: Path, node: str) -> str:
    """Show every model-fallback record this repository holds for ONE node.

    Read-only by construction: the warning "never refuses or disposes
    work", so its handoff must not offer an act. What it offers is the
    append-only evidence itself -- the observed, cleared and superseded
    lines for that node, in journal order -- which is what an operator
    needs to decide whether the primary is genuinely back.
    """
    journal = shlex.quote(f"{project_root}/{_DISPATCH_JOURNAL_SUBPATH}")
    node_field = shlex.quote(json.dumps({"node": node})[1:-1])
    return f"grep -F acp-model-fallback {journal} | grep -F {node_field}"


def pr_view_command(*, project_root: Path, pr_number: int) -> str:
    return f"cd {_quote(path=project_root)} && gh pr view {pr_number} --web"


def release_to_ready_command(*, project_root: Path, work_item: str) -> str:
    return drive_command(project_root=project_root, action_id=f"move:{work_item}:ready")


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

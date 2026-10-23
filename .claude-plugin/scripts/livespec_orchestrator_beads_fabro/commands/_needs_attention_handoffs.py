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
    "availability_wait_journal_command",
    "clear_acp_availability_hold_command",
    "clear_provider_exhaustion_command",
    "dispatcher_loop_command",
    "drive_command",
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

# The two append-only stages an availability wait is reconstructible from: the
# observed-hold records the filter skipped candidates on, and the containment
# refusals that recorded the wait those skips produced. Both are needed, and in
# opposite directions -- an UNAVAILABLE evidence source empties a chain while
# recording no hold at all, so a pattern naming only the hold stage prints
# nothing for exactly the condition an operator cannot otherwise see.
_AVAILABILITY_WAIT_STAGES = "acp-availability-observed|acp-preflight-refusal"

# NO `--reason` IS RENDERED INTO EITHER CLEARANCE VALVE, and the omission is the
# justification rather than a gap in it. A clearance "asserts the entitlement is
# available again, which no observation supports", so the reason is the human act
# the valve exists to record -- but both valves refuse only a BLANK one, so a
# rendered placeholder is ACCEPTED: an operator running the advertised handoff
# verbatim performs the irreversible clearance and persists the placeholder
# itself as the recorded justification, which is a clearance whose audit record
# states nothing. `--reason` is `required=True` in both argparse surfaces, so
# omitting it yields a usage error naming the flag, which is what makes the
# operator state one -- exactly as the omitted `--invoker` already does.


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


def clear_acp_availability_hold_command(
    *,
    project_root: Path,
    scope: str,
    hold_key: str,
    candidate_key: str | None,
) -> str:
    """Retire ONE typed observed-availability record, by its exact identity.

    The EXACT target is what the clause asks for — "exact scope/key clearance
    for current records" — and the valve enforces it: a candidate-scoped
    clearance that omits its `--candidate-key`, or a domain-scoped one that
    supplies it, is refused outright. So the key is rendered when and only when
    the record carries one.

    NEITHER `--invoker` NOR `--reason` IS RENDERED, and both omissions are the
    attribution rather than a gap in it. The valve resolves the invoker itself
    and refuses any invocation that resolves to the unattributed mark, and it
    requires a `--reason` it refuses only when blank — naming, in each case,
    exactly what satisfies the requirement. So an operator who runs this
    verbatim without an identity or a justification is told exactly that, while
    a rendered placeholder for either would be ACCEPTED and would record a
    clearance attributed to nobody, or justified by the placeholder itself.
    """
    exact = f"--scope {shlex.quote(scope)} --hold-key {shlex.quote(hold_key)}"
    if candidate_key is not None:
        exact = f"{exact} --candidate-key {shlex.quote(candidate_key)}"
    return (
        f"python3 {_quote(path=_wrapper_path(name='dispatcher.py'))} "
        f"clear-acp-availability-hold --repo {_quote(path=project_root)} {exact}"
    )


def clear_provider_exhaustion_command(*, project_root: Path, provider: str) -> str:
    """Retire the LEGACY provider-wide exhaustion record for one vendor.

    The sibling of the valve above and deliberately not interchangeable with
    it: a legacy record is scoped to a whole vendor and carries no scope, hold
    key or candidate key, so the typed valve's exactness refusal could never be
    satisfied for one. The two write different journal stages, and neither scan
    reads the other's, so offering the wrong valve here would advertise a
    clearance that retires nothing.

    It renders no `--reason` either, for the reason the module comment above
    gives: this valve carries the identical blank-only refusal, so a placeholder
    rendered here would be accepted just as readily.
    """
    return (
        f"python3 {_quote(path=_wrapper_path(name='dispatcher.py'))} "
        f"clear-provider-exhaustion --repo {_quote(path=project_root)} "
        f"--provider {shlex.quote(provider)}"
    )


def availability_wait_journal_command(*, project_root: Path) -> str:
    """Show the recorded availability wait and the observations behind it.

    The INSPECTION handoff the wait item carries when no live hold is its
    target: "Otherwise its handoff MUST inspect the recorded wait and
    unavailable or failed observation; it MUST NOT advertise clearance of a
    nonexistent live hold." Read-only by construction, exactly as
    `model_fallback_journal_command` beside it is -- an operator reading this
    row cannot clear anything, because there is nothing live to clear, so the
    handoff must offer evidence rather than an act.
    """
    journal = shlex.quote(f"{project_root}/{_DISPATCH_JOURNAL_SUBPATH}")
    return f"grep -E {shlex.quote(_AVAILABILITY_WAIT_STAGES)} {journal}"


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

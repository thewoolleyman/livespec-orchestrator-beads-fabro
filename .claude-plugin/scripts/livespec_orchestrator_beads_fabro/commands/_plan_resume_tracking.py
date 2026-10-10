"""Required-result and budget reconciliation for a typed plan pointer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_child_edges import (
    plan_child_ids_from_dependencies,
    plan_child_ids_from_id_hierarchy,
)
from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    LEGACY_TRACKING,
    NextAction,
    ResumeDirective,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "result_observation",
    "tracked_resume_directive",
]


def tracked_resume_directive(
    *,
    config: StoreConfig,
    epic_id: str,
    action: NextAction,
    observation: ResultObservation | None,
    findings: tuple[str, ...],
) -> ResumeDirective | None:
    """Return a terminal tracking directive, or permit bounded continuation."""
    if observation is None:
        finding = "plan-progress-tracking: missing — pointer carries no required_result and budget"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
        )
    if observation.status == OBSERVATION_SATISFIED:
        next_action = _next_ready_child_action(config=config, epic_id=epic_id)
        finding = (
            f"next_action stale: observed {observation.target} satisfied via"
            f" {observation.evidence}; derived next ledger step"
        )
        if next_action is not None:
            finding = f"{finding} {next_action}"
        return ResumeDirective(
            ask=False,
            next_action=next_action,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if observation.status != OBSERVATION_UNSATISFIED:
        finding = f"next_action result is unobservable: {observation.detail}"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if _budget_unexpired(budget=action.budget):
        return None
    finding = f"next_action obligation expired after observing {observation.target}"
    return ResumeDirective(
        ask=False,
        next_action=None,
        reason=finding,
        findings=(*findings, finding),
        observation=observation,
    )


def result_observation(*, config: StoreConfig, action: NextAction) -> ResultObservation | None:
    """Read an explicitly tracked pointer; legacy pointers retain their old path."""
    if action.required_result is LEGACY_TRACKING or action.required_result is None:
        return None
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    return read_result(
        project_root=project_root,
        reference=action.required_result,
        runner=ShellCommandRunner(),
    )


def _next_ready_child_action(*, config: StoreConfig, epic_id: str) -> str | None:
    """Return this plan's first canonically-ranked ready child, if one exists."""
    records = make_beads_client(config=config).list_issues()
    child_ids = plan_child_ids_from_dependencies(records=records, epic_id=epic_id) | (
        plan_child_ids_from_id_hierarchy(records=records, epic_id=epic_id)
    )
    items = list(
        materialize_work_items(records=read_work_items(path=config.work_items_path)).values()
    )
    ranked_positions = {
        candidate["work_item_ref"]: position
        for position, candidate in enumerate(rank_candidates(items=items))
    }
    ready_children = child_ids & ranked_positions.keys()
    if not ready_children:
        return None
    work_item_ref = min(ready_children, key=ranked_positions.__getitem__)
    return f"impl:{work_item_ref}"


def _budget_unexpired(*, budget: object) -> bool:
    fields = cast("dict[str, Any]", budget)
    deadline = cast("str", fields["deadline"])
    maximum = cast("int", fields["max_handoffs"])
    count = cast("int", fields.get("handoff_count", 0))
    if count >= maximum:
        return False
    return not instant_expired(until=deadline, now=utc_now_iso())

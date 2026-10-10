"""Reconcile a typed plan pointer and decide whether resume asks or acts.

The pointer's required result is read before any continuation decision.  A
satisfied result is stale even if a factory run remains alive; an unsatisfied
result must still fit inside its original budget.  Only after those checks may
an unattended session, or an attended session carrying a current continuation
ruling, take one of the sanctioned executable kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    ContinuationRuling,
    current_continuation_ruling,
    instant_expired,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    missing_section_finding,
    missing_section_gap_text,
    plan_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    AWAIT_KIND,
    HUMAN_KIND,
    IMPL_KIND,
    LEGACY_TRACKING,
    NEXT_ACTION_METADATA_KEY,
    NONE_KIND,
    PLAN_RESUME_ACTOR,
    NextAction,
    ResumeDirective,
    dispatchable_action_id,
    parse_next_action,
    plan_record_metadata,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNSATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "decide_plan_resume",
]

_DESCRIPTION_FIELD = "description"


@dataclass(frozen=True, kw_only=True)
class _ContinuationState:
    """The reconciled inputs to the final continuation decision."""

    config: StoreConfig
    epic_id: str
    unattended: bool
    action: NextAction
    identifier: str
    observation: ResultObservation | None
    findings: tuple[str, ...]


def decide_plan_resume(*, config: StoreConfig, epic_id: str, unattended: bool) -> ResumeDirective:
    """Decide whether this resume asks which action to take, or takes it."""
    record = make_beads_client(config=config).show_issue(issue_id=epic_id)
    action = parse_next_action(
        value=plan_record_metadata(record=record).get(NEXT_ACTION_METADATA_KEY)
    )
    findings = _definition_of_done_findings(record=record, epic_id=epic_id)
    if findings and unattended and not _is_impl(action=action):
        return _gap_directive(config=config, epic_id=epic_id, findings=findings)
    if action is None:
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason=f"epic {epic_id} carries no typed next_action",
            findings=findings,
        )
    identifier = dispatchable_action_id(action=action)
    if identifier is None:
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason=_picker_reason(action=action),
            findings=findings,
        )
    observation = _result_observation(config=config, action=action)
    tracked = _tracked_directive(
        action=action,
        observation=observation,
        findings=findings,
    )
    if tracked is not None:
        return tracked
    return _continuation_directive(
        state=_ContinuationState(
            config=config,
            epic_id=epic_id,
            unattended=unattended,
            action=action,
            identifier=identifier,
            observation=observation,
            findings=findings,
        )
    )


def _tracked_directive(
    *,
    action: NextAction,
    observation: ResultObservation | None,
    findings: tuple[str, ...],
) -> ResumeDirective | None:
    if observation is not None and observation.status == OBSERVATION_SATISFIED:
        finding = (
            f"next_action stale: observed {observation.target} satisfied via"
            f" {observation.evidence}; derive the next step from the ledger"
        )
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if observation is not None and observation.status != OBSERVATION_UNSATISFIED:
        finding = f"next_action result is unobservable: {observation.detail}"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if observation is None or _budget_unexpired(budget=action.budget):
        return None
    finding = f"next_action obligation expired after observing {observation.target}"
    return ResumeDirective(
        ask=False,
        next_action=None,
        reason=finding,
        findings=(*findings, finding),
        observation=observation,
    )


def _continuation_directive(*, state: _ContinuationState) -> ResumeDirective:
    ruling = _ruling(
        config=state.config,
        epic_id=state.epic_id,
        unattended=state.unattended,
    )
    if not state.unattended and ruling is None:
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason="interactive resume",
            findings=state.findings,
            picker_default=state.identifier,
            observation=state.observation,
        )
    if state.action.kind == AWAIT_KIND and state.observation is not None:
        reason = f"waiting for unsatisfied required result {state.observation.target}"
        if ruling is not None:
            reason = f"{reason} under {ruling.identity}"
        return ResumeDirective(
            ask=False,
            next_action=state.identifier,
            reason=reason,
            findings=state.findings,
            observation=state.observation,
        )
    reason = "unattended resume takes the typed next_action"
    if ruling is not None:
        reason = f"attended resume acts under {ruling.identity}"
    return ResumeDirective(
        ask=False,
        next_action=state.identifier,
        reason=reason,
        findings=state.findings,
        observation=state.observation,
    )


def _ruling(*, config: StoreConfig, epic_id: str, unattended: bool) -> ContinuationRuling | None:
    if unattended:
        return None
    return current_continuation_ruling(
        config=config,
        epic_id=epic_id,
        now=utc_now_iso(),
    )


def _result_observation(*, config: StoreConfig, action: NextAction) -> ResultObservation | None:
    """Read an explicitly tracked pointer; legacy pointers retain their old path."""
    if action.required_result is LEGACY_TRACKING or action.required_result is None:
        return None
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    return read_result(
        project_root=project_root,
        reference=action.required_result,
        runner=ShellCommandRunner(),
    )


def _budget_unexpired(*, budget: object) -> bool:
    fields = cast("dict[str, Any]", budget)
    deadline = cast("str", fields["deadline"])
    maximum = cast("int", fields["max_handoffs"])
    count = cast("int", fields.get("handoff_count", 0))
    if count >= maximum:
        return False
    return not instant_expired(until=deadline, now=utc_now_iso())


def _is_impl(*, action: NextAction | None) -> bool:
    return action is not None and action.kind == IMPL_KIND


def _definition_of_done_findings(*, record: BeadsRecord, epic_id: str) -> tuple[str, ...]:
    description = record.get(_DESCRIPTION_FIELD)
    text = description if isinstance(description, str) else ""
    if plan_definition_of_done(description=text).present:
        return ()
    return (missing_section_finding(epic_id=epic_id),)


def _gap_directive(
    *, config: StoreConfig, epic_id: str, findings: tuple[str, ...]
) -> ResumeDirective:
    _ = set_next_action(
        config=config,
        epic_id=epic_id,
        action=NextAction(kind=HUMAN_KIND, ref="", text=missing_section_gap_text()),
        session=PLAN_RESUME_ACTOR,
        now=utc_now_iso(),
    )
    return ResumeDirective(
        ask=True,
        next_action=None,
        reason=f"epic {epic_id} carries no plan Definition of Done section",
        findings=findings,
    )


def _picker_reason(*, action: NextAction) -> str:
    if action.kind in (HUMAN_KIND, NONE_KIND):
        return f"next_action kind {action.kind} raises the picker"
    if action.ref.strip() == "":
        return f"next_action kind {action.kind} carries an empty ref"
    return f"next_action kind {action.kind} raises the picker"

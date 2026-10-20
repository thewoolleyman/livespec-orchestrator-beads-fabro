"""Reconcile a typed plan pointer against its required result, then decide who acts.

Split out of `_plan_resume`, which keeps the TOP-LEVEL resume sequence: the
durable progress check, the missing-Definition-of-Done pre-emption, the pointer
parse and the picker reasons. This module owns the one concern that follows all
of those — given a dispatchable pointer, reconcile it against its target's
actual state and decide whether this session may take it.

The cut is at ONE public entry point, `reconciled_directive`, and every private
helper below it is used only from here: the continuation ruling lookup, the
factory-run liveness read, and the `await` pointer rewrite. `ContinuationState`
and `reconciled_directive` are public because they are the only two names that
cross the module boundary.

The pointer's required result is read before any continuation decision.  A
satisfied result is stale even if a factory run remains alive; an unsatisfied
result must still fit inside its original budget.  Only after those checks may
an unattended session, or an attended session carrying a current continuation
ruling, take one of the sanctioned executable kinds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    ContinuationRuling,
    current_continuation_ruling,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    AWAIT_KIND,
    IMPL_KIND,
    PLAN_RESUME_ACTOR,
    SPEC_OP_KIND,
    NextAction,
    ResumeDirective,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    ResultObservation,
)
from livespec_orchestrator_beads_fabro.commands._plan_resume_advance import (
    AdvanceRequest,
    advance_after_satisfied_result,
)
from livespec_orchestrator_beads_fabro.commands._plan_resume_tracking import (
    result_observation,
    tracked_resume_directive,
)
from livespec_orchestrator_beads_fabro.commands._plan_run_liveness import (
    LIVENESS_LIVE,
    LIVENESS_NOT_LIVE,
    LIVENESS_UNOBSERVABLE,
    RunLiveness,
    observe_target_run,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ContinuationState",
    "reconciled_directive",
]


@dataclass(frozen=True, kw_only=True)
class ContinuationState:
    """The reconciled inputs to the final continuation decision."""

    config: StoreConfig
    epic_id: str
    unattended: bool
    action: NextAction
    identifier: str
    observation: ResultObservation | None
    findings: tuple[str, ...]


def reconciled_directive(
    *,
    config: StoreConfig,
    epic_id: str,
    unattended: bool,
    action: NextAction,
    identifier: str,
    findings: tuple[str, ...],
) -> ResumeDirective:
    """Reconcile the pointer against its required result, then decide who acts.

    The two reconciliation findings are evaluated IN THE CLAUSE'S ORDER, and the
    order is explicit HERE rather than buried inside one reconciler: a stale
    pointer must never reach the factory, so a factory outage cannot mask the
    staleness this resume owes its reader.
    """
    observation = result_observation(config=config, epic_id=epic_id, action=action)
    if observation is not None and observation.status == OBSERVATION_SATISFIED:
        return advance_after_satisfied_result(
            request=AdvanceRequest(
                config=config,
                epic_id=epic_id,
                action=action,
                observation=observation,
                findings=findings,
                unattended=unattended,
                ruling_identity=_ruling_identity(
                    config=config, epic_id=epic_id, unattended=unattended
                ),
            )
        )
    tracked = tracked_resume_directive(
        action=action,
        observation=observation,
        findings=findings,
    )
    if tracked is not None:
        return tracked
    liveness = _target_run_liveness(config=config, epic_id=epic_id, action=action)
    if liveness.verdict == LIVENESS_UNOBSERVABLE:
        finding = f"next_action target run liveness is unobservable: {liveness.detail}"
        return ResumeDirective(
            ask=False,
            next_action=None,
            reason=finding,
            findings=(*findings, finding),
            observation=observation,
        )
    if liveness.verdict == LIVENESS_LIVE:
        action = _awaiting_action(
            config=config,
            epic_id=epic_id,
            action=action,
            run_id=liveness.run_id,
        )
        identifier = f"{AWAIT_KIND}:{action.ref}"
    return _continuation_directive(
        state=ContinuationState(
            config=config,
            epic_id=epic_id,
            unattended=unattended,
            action=action,
            identifier=identifier,
            observation=observation,
            findings=findings,
        )
    )


def _continuation_directive(*, state: ContinuationState) -> ResumeDirective:
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


def _ruling_identity(*, config: StoreConfig, epic_id: str, unattended: bool) -> str | None:
    ruling = _ruling(config=config, epic_id=epic_id, unattended=unattended)
    return None if ruling is None else ruling.identity


def _target_run_liveness(
    *,
    config: StoreConfig,
    epic_id: str,
    action: NextAction,
) -> RunLiveness:
    """Ask the factory only for the pointers the LIVE RUN finding governs.

    The clause scopes the question to an `impl` or `spec-op` pointer whose
    required result is still unsatisfied, so every other KIND answers not-live
    WITHOUT a round trip. The unsatisfied half of that scope is already
    established by the caller: `tracked_resume_directive` returns a terminal
    directive for a satisfied, unobservable or out-of-budget obligation, so this
    is reached only for an in-budget unsatisfied one. That ordering is what
    keeps the SATISFIED finding strictly first — a stale pointer reaches no
    factory at all, so a factory outage can never mask the staleness the resume
    must report.
    """
    if action.kind not in (IMPL_KIND, SPEC_OP_KIND):
        return RunLiveness(
            verdict=LIVENESS_NOT_LIVE,
            run_id=None,
            detail=f"no factory run drives a {action.kind} pointer",
        )
    return observe_target_run(config=config, epic_id=epic_id, action=action)


def _awaiting_action(
    *,
    config: StoreConfig,
    epic_id: str,
    action: NextAction,
    run_id: str | None,
) -> NextAction:
    rewritten = replace(
        action,
        kind=AWAIT_KIND,
        ref=f"run:{run_id}",
        text=f"Wait for live factory run {run_id}.",
    )
    _ = set_next_action(
        config=config,
        epic_id=epic_id,
        action=rewritten,
        session=PLAN_RESUME_ACTOR,
        now=utc_now_iso(),
    )
    return rewritten

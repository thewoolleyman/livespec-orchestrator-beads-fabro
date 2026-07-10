"""Cost-wave loop helper for `_dispatcher_cost.gate_wave`."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_ENFORCE,
    CostGateDecision,
    CostObservation,
    JournalWriter,
    cap_value_decision,
    cost_gate_decision,
    observe_run_cost,
    resolve_per_run_cap_usd,
    resolve_per_session_cap_usd,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import parse_run_id_for_work_item

__all__: list[str] = ["gate_wave_refusals"]


def gate_wave_refusals(  # noqa: PLR0913 - mirrors the public gate_wave inputs.
    *,
    mode: str,
    outcomes: tuple[DispatchOutcome, ...],
    ps_json: str,
    journal: JournalWriter,
    environ: dict[str, str] | None,
    derived_cost_micros_by_work_item: dict[str, int] | None,
    cost_mode: str,
) -> tuple[str, ...]:
    refusals: list[str] = []
    session_usd_micros = 0
    derived = derived_cost_micros_by_work_item or {}
    enforcing = cost_mode == COST_MODE_ENFORCE
    per_run_cap = resolve_per_run_cap_usd(environ=environ) if environ is not None else None
    per_session_cap = resolve_per_session_cap_usd(environ=environ) if environ is not None else None
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        run_id = parse_run_id_for_work_item(ps_json=ps_json, work_item_id=outcome.work_item_id)
        if run_id is None:
            _append_skipped(journal=journal, work_item_id=outcome.work_item_id)
            continue
        observation = _observe_with_derived(
            ps_json=ps_json,
            run_id=run_id,
            derived_micros=derived.get(outcome.work_item_id),
        )
        usd_micros = observation.usd_micros
        if usd_micros is not None:
            session_usd_micros += usd_micros
        decision = _decision(
            enforcing=enforcing,
            mode=mode,
            run_id=run_id,
            observation=observation,
            usd_micros=usd_micros,
            session_usd_micros=session_usd_micros,
            per_run_cap=per_run_cap,
            per_session_cap=per_session_cap,
        )
        _append_gate(
            journal=journal,
            work_item_id=outcome.work_item_id,
            run_id=run_id,
            observation=observation,
            session_usd_micros=session_usd_micros,
            decision=decision,
        )
        if decision.refuse:
            refusals.append(outcome.work_item_id)
    return tuple(refusals)


def _decision(  # noqa: PLR0913 - keeps the cost-mode branch explicit and typed.
    *,
    enforcing: bool,
    mode: str,
    run_id: str,
    observation: CostObservation,
    usd_micros: int | None,
    session_usd_micros: int,
    per_run_cap: float | None,
    per_session_cap: float | None,
) -> CostGateDecision:
    if not enforcing:
        return _report_decision(run_id=run_id, observation=observation)
    if usd_micros is not None and per_run_cap is not None and per_session_cap is not None:
        return cap_value_decision(
            run_id=run_id,
            usd_micros=usd_micros,
            per_run_cap_usd=per_run_cap,
            session_usd_micros_after=session_usd_micros,
            per_session_cap_usd=per_session_cap,
        )
    return cost_gate_decision(mode=mode, observation=observation)


def _append_skipped(*, journal: JournalWriter, work_item_id: str) -> None:
    journal.append(
        record={
            "stage": "cost-gate-skipped",
            "work_item_id": work_item_id,
            "reason": "could not resolve the run id from `fabro ps -a --json`",
        }
    )


def _append_gate(
    *,
    journal: JournalWriter,
    work_item_id: str,
    run_id: str,
    observation: CostObservation,
    session_usd_micros: int,
    decision: CostGateDecision,
) -> None:
    journal.append(
        record={
            "stage": "cost-gate",
            "work_item_id": work_item_id,
            "run_id": run_id,
            "observable": observation.observable,
            "usd_micros": observation.usd_micros,
            "session_usd_micros": session_usd_micros,
            "refuse": decision.refuse,
            "severity": decision.severity,
            "reason": decision.reason,
        }
    )


def _report_decision(*, run_id: str, observation: CostObservation) -> CostGateDecision:
    if observation.observable:
        return CostGateDecision(
            refuse=False,
            severity="report",
            reason=(
                f"run {run_id} cost reported "
                f"({observation.usd_micros} usd_micros); report-only, never enforced"
            ),
        )
    return CostGateDecision(
        refuse=False,
        severity="report",
        reason=(
            f"run {run_id} cost is unobservable (no CC token telemetry / fabro "
            f"total_usd_micros null); report-only, never enforced"
        ),
    )


def _observe_with_derived(
    *, ps_json: str, run_id: str, derived_micros: int | None
) -> CostObservation:
    if derived_micros is not None:
        return CostObservation(run_id=run_id, usd_micros=derived_micros, observable=True)
    return observe_run_cost(ps_json=ps_json, run_id=run_id)

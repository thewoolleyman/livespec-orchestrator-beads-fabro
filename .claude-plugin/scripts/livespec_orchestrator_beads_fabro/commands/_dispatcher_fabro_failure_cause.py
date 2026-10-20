"""Derive the failing stage's cause before terminal disposition."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    routing_stage_failure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import causal_stage_failure
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

__all__: list[str] = ["terminal_failure_cause"]


def terminal_failure_cause(*, inspect: FabroInspectResult | None) -> FabroFailureDetail | None:
    """Read the failed routing stage before provider-limit disposition runs."""
    observed = None if inspect is None else inspect.failure
    causal = causal_stage_failure(
        evidence=None if inspect is None else terminal_evidence(payload=inspect.payload)
    )
    if inspect is None or not causal.stages:
        return observed
    routed = routing_stage_failure(
        observed=observed,
        inspect_payload=inspect.payload,
        events_payload=inspect.events_payload,
        stage=causal.stages[-1],
    )
    return routed if routed is not None and routed.cause is not None else observed

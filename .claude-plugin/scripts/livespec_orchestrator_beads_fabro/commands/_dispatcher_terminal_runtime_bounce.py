"""Turn an observed terminal runtime breach into the existing bounce outcome."""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_convergence import (
    RuntimeConvergenceVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
    RECAPTURE_EXHAUSTED_MARKER,
)

__all__: list[str] = ["apply_terminal_runtime_bounce"]


def apply_terminal_runtime_bounce(
    *, outcome: DispatchOutcome, verdict: RuntimeConvergenceVerdict | None
) -> DispatchOutcome:
    """Return the sanctioned bounce only for an otherwise unowned failure."""
    if (
        verdict is None
        or not verdict.bounces
        or outcome.status != "failed"
        or NEEDS_HUMAN_MARKER in outcome.detail
        or RECAPTURE_EXHAUSTED_MARKER in outcome.detail
    ):
        return outcome
    return replace(outcome, detail=f"{NON_CONVERGED_MARKER}: {verdict.as_reason()}")

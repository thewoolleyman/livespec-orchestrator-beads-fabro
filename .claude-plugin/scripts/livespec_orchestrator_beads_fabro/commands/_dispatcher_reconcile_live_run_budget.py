"""The claim-lane route for a live run whose dispatcher is gone.

The route is deliberately named separately from the ordinary ``run-live``
hold.  Reconciliation can only enter it after the claim survey established
that this host owns the stamp and no live process owns its dispatch lock.
The caller supplies the watchdog's verdict; this module keeps the result
vocabulary shared between that route and the claim recovery record.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdictValue,
)

__all__: list[str] = [
    "ACTION_LIVE_RUN_WALL_BUDGET",
    "LiveRunBudgetRecovery",
    "live_run_budget_recovery",
]

ACTION_LIVE_RUN_WALL_BUDGET = "live-run-wall-budget"
_CANCELLED = "run-wall-budget-exceeded"


@dataclass(frozen=True, kw_only=True)
class LiveRunBudgetRecovery:
    """What the wall-budget poll leaves for the claim recovery to finish."""

    cancelled: bool


def live_run_budget_recovery(*, verdict: RunWallVerdictValue) -> LiveRunBudgetRecovery:
    """Classify a watchdog-equivalent budget poll for the claim lane.

    Within-budget and preservation-held polls intentionally collapse to the
    ordinary ``run-live`` hold; only a verified export followed by cancellation
    permits the later blocked/needs-human rest.
    """
    return LiveRunBudgetRecovery(cancelled=verdict.value == _CANCELLED)

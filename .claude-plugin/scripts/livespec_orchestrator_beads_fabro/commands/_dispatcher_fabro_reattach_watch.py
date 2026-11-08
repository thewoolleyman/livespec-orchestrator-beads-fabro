"""Whole-run budget state retained while a dropped client is reattached."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    recorded_running_epoch,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallBudgetWatch,
    )

__all__: list[str] = ["ReattachBudgetWatch"]


@dataclass(kw_only=True)
class ReattachBudgetWatch:
    """The one budget clock that survives each reattach poll."""

    plan: DispatchPlan
    runner: CommandRunner
    journal: JournalWriter
    run_id: str
    wall_clock: Callable[[], float]
    port: FabroPort
    budget: RunWallBudgetWatch

    def verdict(self, *, payload: object | None) -> str:
        """Apply the budget to the running run that the current poll observed."""
        return self.budget.verdict(
            dispatch_id=None,
            plan=self.plan,
            port=self.port,
            runner=self.runner,
            journal=self.journal,
            run_id=self.run_id,
            recorded_epoch=recorded_running_epoch(payload=payload),
            now_epoch=self.wall_clock(),
        ).value

"""What one poll decides about a live run: its whole-run wall budget, then its stall.

The two bounds are one question asked in a fixed order, so the order lives in
one place a watch loop calls rather than in each loop that needs it. A later
observer of the same run (a re-attach supervision) calls `decide_run_watch` with
the run's fixed budget clock and its liveness samples instead of duplicating it.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallBudgetWatch,
    RunWallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_progress import RunWallProgress
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    cancel_stalled_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    quiet_window_seconds,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "RunWatchDecision",
    "decide_run_watch",
]


@dataclass(frozen=True, kw_only=True)
class RunWatchDecision:
    """Which cancel, if any, this poll performed on the run.

    Both false is "keep polling": within budget and not stalled, a budget export
    held for one more poll, or a stall cancel the server refused.
    """

    budget_exceeded: bool = False
    stalled: bool = False


def decide_run_watch(  # noqa: PLR0913 — kw-only per-poll decision; the dispatch, the three seams, the run, the budget clock, the liveness window and the two clock readings are independent inputs.
    *,
    budget: RunWallBudgetWatch,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
    recorded_epoch: float | None,
    now_epoch: float,
    samples: tuple[LivenessSample, ...],
    stall_seconds: float,
    progress: RunWallProgress | None = None,
    stream_observable: bool | None = None,
    new_completions: tuple[tuple[str, float], ...] = (),
) -> RunWatchDecision:
    """Take this poll's cancel decision for a run observed `running`."""
    # BEFORE the stall decision, which is the clause's own precedence:
    # a quiet run past its budget satisfies both rules, and only the
    # budget disposition rests it for a person.
    verdict = budget.verdict(
        dispatch_id=dispatch_id,
        plan=plan,
        port=port,
        runner=runner,
        journal=journal,
        run_id=run_id,
        recorded_epoch=recorded_epoch,
        now_epoch=now_epoch,
        progress=progress,
        stream_observable=stream_observable,
        new_completions=new_completions,
    )
    if verdict == RunWallVerdict.CANCELLED:
        return RunWatchDecision(budget_exceeded=True)
    if verdict == RunWallVerdict.HELD:
        # A HELD verdict is NOT a fall-through: the clause requires that
        # a run whose budget export is pending its read-back "is not
        # cancelled as stalled-no-progress" either, and a quiet run past
        # its budget satisfies the stall rule too.
        return RunWatchDecision()
    if verdict == RunWallVerdict.CONTINUED:
        return RunWatchDecision()
    # A cancel the server refused falls through: the run may still be
    # live, so the watch keeps polling and asks again.
    if decide_stall(
        samples=samples, stall_seconds=stall_seconds
    ) == StallVerdict.STALLED and cancel_stalled_run(
        dispatch_id=dispatch_id,
        plan=plan,
        port=port,
        journal=journal,
        run_id=run_id,
        quiet_seconds=quiet_window_seconds(samples=samples),
    ):
        return RunWatchDecision(stalled=True)
    return RunWatchDecision()

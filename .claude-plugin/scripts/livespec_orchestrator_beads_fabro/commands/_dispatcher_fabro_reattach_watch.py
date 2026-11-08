"""Supervise a live run after its foreground Fabro client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_stall_watch import (
    ReattachStallWatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    recorded_running_epoch,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    FabroPort,
    fabro_port_for_plan,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
        LedgerComments,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallBudgetWatch,
    )

__all__: list[str] = [
    "ReattachBudgetWatch",
    "ReattachObservationInputs",
    "ReattachTiming",
    "observe_reattached_run",
]

_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
_REATTACH_WINDOW_SECONDS = 600.0
_MAX_UNANSWERED_INSPECTS = 12
_TERMINAL_STATUS_KINDS = frozenset(
    {"succeeded", "failed", "cancelled", "canceled", "blocked", "human_input_required"}
)
_LIVE_STATUS_KINDS = frozenset({"running", "runnable", "pending", "queued", "starting", "paused"})


@dataclass(frozen=True, kw_only=True)
class ReattachTiming:
    """The clocks and waiting seam of one reattach supervision loop."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time


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


@dataclass(frozen=True, kw_only=True)
class ReattachObservationInputs:
    """Dependencies and facts for supervision after a client stream drops."""

    plan: DispatchPlan
    runner: CommandRunner
    journal: JournalWriter
    run_id: str
    follow_live: bool
    timing: ReattachTiming
    ledger_resolver: Callable[..., LedgerComments | None] | None = None
    budget_factory: Callable[..., RunWallBudgetWatch] | None = None


def observe_reattached_run(*, inputs: ReattachObservationInputs) -> FabroInspectResult:
    """Inspect one run, retaining budget and stall supervision after a client drop."""
    watch = ReattachBudgetWatch(
        plan=inputs.plan,
        runner=inputs.runner,
        journal=inputs.journal,
        run_id=inputs.run_id,
        wall_clock=inputs.timing.wall_clock,
        port=fabro_port_for_plan(plan=inputs.plan, runner=inputs.runner),
        budget=(inputs.budget_factory or _budget_watch)(
            ledger=(inputs.ledger_resolver or _run_wall_ledger)(repo=inputs.plan.repo)
        ),
    )
    return _observe_with_watch(
        plan=inputs.plan,
        journal=inputs.journal,
        run_id=inputs.run_id,
        follow_live=inputs.follow_live,
        timing=inputs.timing,
        watch=watch,
    )


def _run_wall_ledger(*, repo: Path) -> LedgerComments | None:
    """Resolve the ledger lazily, after the engine's import graph has settled."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
        run_wall_ledger,
    )

    return run_wall_ledger(repo=repo)


def _budget_watch(*, ledger: LedgerComments | None) -> RunWallBudgetWatch:
    """Construct the mutable watch without importing it during module initialization."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallBudgetWatch,
    )

    return RunWallBudgetWatch(ledger=ledger)


def _observe_with_watch(
    *,
    plan: DispatchPlan,
    journal: JournalWriter,
    run_id: str,
    follow_live: bool,
    timing: ReattachTiming,
    watch: ReattachBudgetWatch,
) -> FabroInspectResult:
    """Apply bounded reattach reads and the persistent whole-run decisions."""
    unanswered = 0
    attempt = 0
    deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
    stall = ReattachStallWatch(
        plan=plan, journal=journal, run_id=run_id, timing=timing, port=watch.port
    )
    while True:
        inspect = watch.port.inspect(
            run_id=run_id,
            timeout_seconds=_inspect_timeout(
                follow_live=follow_live, deadline=deadline, timing=timing
            ),
        )
        journal_stage(
            journal=journal,
            plan=plan,
            stage="fabro-inspect",
            result=cast("CommandResult", inspect.command),
        )
        if follow_live:
            attempt = _journal_reattach_attempt(
                journal=journal, plan=plan, run_id=run_id, attempt=attempt, inspect=inspect
            )
        if not follow_live or _is_terminal(inspect=inspect):
            return inspect
        if _is_live(inspect=inspect):
            verdict = watch.verdict(payload=inspect.payload)
            if verdict == "run-wall-budget-exceeded":
                return replace(inspect, budget_exceeded_run_id=run_id)
            if verdict == "run-wall-budget-held":
                deadline = _next_live_deadline(timing=timing)
                continue
            if inspect.status_kind == "running" and stall.cancel_if_quiet(inspect=inspect):
                return replace(inspect, stalled_run_id=run_id)
            unanswered = 0
            deadline = _next_live_deadline(timing=timing)
            continue
        unanswered += 1
        remaining = deadline - timing.clock()
        if unanswered >= _MAX_UNANSWERED_INSPECTS or remaining <= 0:
            return inspect
        timing.sleep(min(5.0 * 2 ** (unanswered - 1), 60.0, remaining))
        if timing.clock() >= deadline:
            return inspect


def _inspect_timeout(*, follow_live: bool, deadline: float, timing: ReattachTiming) -> float:
    """Keep an inspect from consuming more than the remaining reattach window."""
    if not follow_live:
        return _FABRO_INSPECT_TIMEOUT_SECONDS
    return min(_FABRO_INSPECT_TIMEOUT_SECONDS, max(0.001, deadline - timing.clock()))


def _is_terminal(*, inspect: FabroInspectResult) -> bool:
    """Whether a successful inspect conclusively observed a terminal run."""
    return inspect.command.exit_code == 0 and inspect.status_kind in _TERMINAL_STATUS_KINDS


def _is_live(*, inspect: FabroInspectResult) -> bool:
    """Whether a successful inspect observed a run that can still hold its slot."""
    return inspect.command.exit_code == 0 and inspect.status_kind in _LIVE_STATUS_KINDS


def _next_live_deadline(*, timing: ReattachTiming) -> float:
    """Sleep one live-poll interval and reset the broken-route observation window."""
    timing.sleep(30.0)
    return timing.clock() + _REATTACH_WINDOW_SECONDS


def _journal_reattach_attempt(
    *,
    journal: JournalWriter,
    plan: DispatchPlan,
    run_id: str,
    attempt: int,
    inspect: FabroInspectResult,
) -> int:
    """Write one live-observation attempt and return its next sequence number."""
    next_attempt = attempt + 1
    journal.append(
        record={
            "stage": "fabro-reattach",
            "work_item_id": plan.work_item_id,
            "run_id": run_id,
            "attempt": next_attempt,
            "exit_code": inspect.command.exit_code,
            "status": inspect.status_kind,
            "server_url": plan.fabro_factory_server,
        }
    )
    return next_attempt

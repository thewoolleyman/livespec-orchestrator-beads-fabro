"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_second_reads import (
    executed_candidate_attribution,
    terminal_events_attachment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_unobservable import (
    unobservable_run_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_watch_decision import (
    ReattachRun,
    RunWatchState,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_termination import (
    sandbox_termination_attachment,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    fabro_port_for_plan,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        JournalWriter,
    )

__all__: list[str] = [
    "TERMINAL_STATUS_KINDS",
    "ReattachTiming",
    "inspect_after_run",
    "inspect_run",
    "unobservable_run_outcome",
]

_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
# A broken route must outlive the measured 2m25s tailnet outage without
# trapping a dispatcher indefinitely. The attempt cap also bounds immediate
# refusals; a healthy live observation resets both limits.
_REATTACH_WINDOW_SECONDS = 600.0
_MAX_UNANSWERED_INSPECTS = 12
TERMINAL_STATUS_KINDS = frozenset(
    {"succeeded", "failed", "cancelled", "canceled", "blocked", "human_input_required"}
)
_LIVE_STATUS_KINDS = frozenset({"running", "runnable", "pending", "queued", "starting", "paused"})


@dataclass(frozen=True, kw_only=True)
class ReattachTiming:
    """The clock and waiting seam of one supervision loop."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time


_DEFAULT_TIMING = ReattachTiming()


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | ReattachRun | None,
    follow_live: bool = False,
    timing: ReattachTiming = _DEFAULT_TIMING,
) -> FabroInspectResult | None:
    """Read a run, and attribute a provider ceiling to the candidate that ran.

    The observation itself is `_observed_run` below. What this adds is the one
    thing the observed payload cannot answer: WHICH candidate entitlement the
    failing attempt spent. MEASURED on both engines, an `inspect --json` record
    carries no `labels` key — the pinned build answers `run_id`, `status` and
    `checkpoint`, and the candidate build answers nine keys, none of them
    labels — while the `ps --json` run row carries them on every row. So the
    attribution costs a SECOND read, and it is taken HERE, at the one function
    every dispatch and every reconciliation reads a run through, rather than at
    each of the terminal mappers that consume the failure.

    The STAGE EVENT STREAM is attached for the same reason and at the same seam.
    A terminal node's emitted output reaches neither the `fabro run` client's
    stderr nor the run conclusion's structured failure, so the needs-human
    mapper reading only those two channels could not return a hit for a
    preservation the terminal demonstrably performed — and its clean empty
    answer is indistinguishable from a terminal that preserved nothing.
    """
    if run_id is None:
        return None
    run = run_id if isinstance(run_id, ReattachRun) else ReattachRun(run_id=run_id)
    return sandbox_termination_attachment(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run.run_id,
        inspect=terminal_events_attachment(
            plan=plan,
            runner=runner,
            journal=journal,
            run_id=run.run_id,
            inspect=executed_candidate_attribution(
                plan=plan,
                runner=runner,
                journal=journal,
                run_id=run.run_id,
                inspect=_observed_run(
                    plan=plan,
                    runner=runner,
                    journal=journal,
                    run=run,
                    follow_live=follow_live,
                    timing=timing,
                ),
            ),
        ),
    )


def _observed_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run: ReattachRun,
    follow_live: bool,
    timing: ReattachTiming,
) -> FabroInspectResult:
    """Read a run, optionally supervising it after a lost client stream.

    Only confirmed terminal evidence ends supervision immediately. Failed or
    unrecognized reads use exponential backoff, capped at a minute, for at most
    ten minutes or twelve consecutive unanswered inspections. Inspect timeouts
    consume that same budget. Confirmed live reads reset it and keep polling.
    """
    unanswered = 0
    attempt = 0
    deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
    port = fabro_port_for_plan(plan=plan, runner=runner)
    watch = run.watch_state or _fresh_run_watch(plan=plan, timing=timing)
    while True:
        timeout = (
            min(_FABRO_INSPECT_TIMEOUT_SECONDS, max(0.001, deadline - timing.clock()))
            if follow_live
            else _FABRO_INSPECT_TIMEOUT_SECONDS
        )
        inspect = port.inspect(
            run_id=run.run_id,
            timeout_seconds=timeout,
        )
        journal_stage(
            journal=journal,
            plan=plan,
            stage="fabro-inspect",
            result=cast("CommandResult", inspect.command),
        )
        if follow_live:
            attempt += 1
            journal.append(
                record={
                    "stage": "fabro-reattach",
                    "work_item_id": plan.work_item_id,
                    "run_id": run.run_id,
                    "attempt": attempt,
                    "exit_code": inspect.command.exit_code,
                    "status": inspect.status_kind,
                    "server_url": plan.fabro_factory_server,
                }
            )
        if not follow_live or (
            inspect.command.exit_code == 0 and inspect.status_kind in TERMINAL_STATUS_KINDS
        ):
            return inspect
        if inspect.command.exit_code == 0 and inspect.status_kind in _LIVE_STATUS_KINDS:
            if inspect.status_kind == "running":
                watch.observe_liveness(
                    plan=plan,
                    port=port,
                    run_id=run.run_id,
                    heartbeat_path=None,
                    record=inspect.payload,
                    journal=journal,
                )
                decision = watch.decide(
                    plan=plan,
                    port=port,
                    runner=runner,
                    journal=journal,
                    run_id=run.run_id,
                    record=inspect.payload,
                )
                if decision.budget_exceeded:
                    return replace(inspect, budget_exceeded_run_id=run.run_id)
                if decision.stalled:
                    return replace(inspect, stalled_run_id=run.run_id)
            unanswered = 0
            timing.sleep(30.0)
            deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
            continue
        unanswered += 1
        remaining = deadline - timing.clock()
        if unanswered >= _MAX_UNANSWERED_INSPECTS or remaining <= 0:
            return inspect
        timing.sleep(min(5.0 * 2 ** (unanswered - 1), 60.0, remaining))
        if timing.clock() >= deadline:
            return inspect


def inspect_after_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | ReattachRun | None,
    follow_live: bool,
    sleep: Callable[[float], None],
) -> FabroInspectResult | None:
    """Observe completion and refresh a failed run's not-yet-persisted detail."""
    inspect = inspect_run(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        follow_live=follow_live,
        timing=ReattachTiming(sleep=sleep),
    )
    if (
        follow_live
        and run_id is not None
        and (
            inspect is not None
            and inspect.command.exit_code == 0
            and inspect.status_kind == "failed"
            and inspect.failure is None
        )
    ):
        refreshed = inspect_run(plan=plan, runner=runner, journal=journal, run_id=run_id)
        if refreshed is not None and refreshed.failure is not None:
            inspect = refreshed
    return inspect


def _fresh_run_watch(*, plan: DispatchPlan, timing: ReattachTiming) -> RunWatchState:
    """Construct the watch after the engine's import graph has settled."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        LivenessState,
        liveness_sample,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
        run_wall_ledger,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallBudgetWatch,
    )

    return RunWatchState(
        budget=RunWallBudgetWatch(ledger=run_wall_ledger(repo=plan.repo)),
        dispatch_id=None,
        liveness_state=LivenessState(),
        sample_liveness=liveness_sample,
        liveness_clock=timing.clock,
        wall_clock=timing.wall_clock,
    )

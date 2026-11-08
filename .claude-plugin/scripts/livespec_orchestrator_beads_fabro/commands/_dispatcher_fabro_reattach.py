"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_outcome import (
    unobservable_run_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_watch import (
    ReattachBudgetWatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_second_reads import (
    executed_candidate_attribution,
    terminal_events_attachment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    quiet_window_seconds,
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
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        LivenessState,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
        LedgerComments,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
        RunWallBudgetWatch,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import LivenessSample

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


# Each sentinel a TERMINAL node prints on the client's own channel before the
# client exits non-green. `DEAD_IMPLEMENTER_SENTINEL` covers its check-failed
# variant too, which carries it as a prefix.
@dataclass(frozen=True, kw_only=True)
class ReattachTiming:
    """The clock and waiting seam of one supervision loop."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time


_DEFAULT_TIMING = ReattachTiming()


def _liveness_state() -> object:
    """Construct liveness state after the engine's reattach import has settled."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        LivenessState,
    )

    return LivenessState()


@dataclass(frozen=True, kw_only=True)
class _ReattachLivenessInput:
    """All of one reattach poll's liveness inputs."""

    plan: DispatchPlan
    port: FabroPort
    run_id: str
    observed_at: float
    state: object
    run_record: object | None
    journal: JournalWriter


def liveness_sample(*, inputs: _ReattachLivenessInput) -> LivenessSample:
    """Take a liveness sample without importing the engine through this module."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
        liveness_sample as resolved_liveness_sample,
    )

    return resolved_liveness_sample(
        plan=inputs.plan,
        port=inputs.port,
        run_id=inputs.run_id,
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=inputs.observed_at,
        state=cast("LivenessState", inputs.state),
        run_record=inputs.run_record,
        journal=inputs.journal,
    )


@dataclass(frozen=True, kw_only=True)
class _ReattachStallCancelInput:
    """All facts needed to cancel one reattached stalled run."""

    plan: DispatchPlan
    port: FabroPort
    journal: JournalWriter
    run_id: str
    quiet_seconds: float | None


def cancel_stalled_run(*, inputs: _ReattachStallCancelInput) -> bool:
    """Cancel lazily so reattach remains importable while the engine initializes."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
        cancel_stalled_run as resolved_cancel_stalled_run,
    )

    return resolved_cancel_stalled_run(
        dispatch_id=None,
        plan=inputs.plan,
        port=inputs.port,
        journal=inputs.journal,
        run_id=inputs.run_id,
        quiet_seconds=inputs.quiet_seconds,
    )


@dataclass(kw_only=True)
class _ReattachStallWatch:
    """Liveness evidence retained while a reattached running run is observed."""

    plan: DispatchPlan
    journal: JournalWriter
    run_id: str
    timing: ReattachTiming
    watch: ReattachBudgetWatch
    liveness_state: object = field(default_factory=_liveness_state)
    samples: list[LivenessSample] = field(default_factory=list)

    def cancel_if_quiet(self, *, inspect: FabroInspectResult) -> bool:
        """Cancel only when the retained event stream confirms a full quiet window."""
        self.samples.append(
            liveness_sample(
                inputs=_ReattachLivenessInput(
                    plan=self.plan,
                    port=self.watch.port,
                    run_id=self.run_id,
                    observed_at=self.timing.clock(),
                    state=self.liveness_state,
                    run_record=inspect.payload,
                    journal=self.journal,
                )
            )
        )
        window = tuple(self.samples)
        stalled = decide_stall(samples=window, stall_seconds=self.plan.stall_window.seconds)
        if stalled != StallVerdict.STALLED:
            return False
        return cancel_stalled_run(
            inputs=_ReattachStallCancelInput(
                plan=self.plan,
                port=self.watch.port,
                journal=self.journal,
                run_id=self.run_id,
                quiet_seconds=quiet_window_seconds(samples=window),
            )
        )


def run_wall_ledger(*, repo: Path) -> LedgerComments | None:
    """Resolve the budget ledger after the engine has finished importing."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
        run_wall_ledger as resolved_run_wall_ledger,
    )

    return resolved_run_wall_ledger(repo=repo)


def _run_wall_budget_watch(*, ledger: LedgerComments | None) -> RunWallBudgetWatch:
    """Load the watch lazily so the engine's re-attach import remains acyclic."""
    watch_type = cast("type[RunWallBudgetWatch] | None", globals().get("RunWallBudgetWatch"))
    if watch_type is None:
        from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
            RunWallBudgetWatch as ResolvedRunWallBudgetWatch,
        )

        watch_type = ResolvedRunWallBudgetWatch
    return watch_type(ledger=ledger)


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
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
    return terminal_events_attachment(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        inspect=executed_candidate_attribution(
            plan=plan,
            runner=runner,
            journal=journal,
            run_id=run_id,
            inspect=_observed_run(
                plan=plan,
                runner=runner,
                journal=journal,
                run_id=run_id,
                follow_live=follow_live,
                timing=timing,
            ),
        ),
    )


def _observed_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str,
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
    watch = ReattachBudgetWatch(
        plan=plan,
        runner=runner,
        journal=journal,
        run_id=run_id,
        wall_clock=timing.wall_clock,
        port=fabro_port_for_plan(plan=plan, runner=runner),
        budget=_run_wall_budget_watch(ledger=run_wall_ledger(repo=plan.repo)),
    )
    stall_watch = _ReattachStallWatch(
        plan=plan, journal=journal, run_id=run_id, timing=timing, watch=watch
    )
    while True:
        timeout = (
            min(_FABRO_INSPECT_TIMEOUT_SECONDS, max(0.001, deadline - timing.clock()))
            if follow_live
            else _FABRO_INSPECT_TIMEOUT_SECONDS
        )
        inspect = watch.port.inspect(
            run_id=run_id,
            timeout_seconds=timeout,
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
        if not follow_live or (
            inspect.command.exit_code == 0 and inspect.status_kind in TERMINAL_STATUS_KINDS
        ):
            return inspect
        if inspect.command.exit_code == 0 and inspect.status_kind in _LIVE_STATUS_KINDS:
            verdict = watch.verdict(payload=inspect.payload)
            if verdict == "run-wall-budget-exceeded":
                return replace(inspect, budget_exceeded_run_id=run_id)
            if verdict == "run-wall-budget-held":
                timing.sleep(30.0)
                deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
                continue
            if inspect.status_kind == "running" and stall_watch.cancel_if_quiet(inspect=inspect):
                return replace(inspect, stalled_run_id=run_id)
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


def _journal_reattach_attempt(
    *,
    journal: JournalWriter,
    plan: DispatchPlan,
    run_id: str,
    attempt: int,
    inspect: FabroInspectResult,
) -> int:
    """Write the live-observation attempt and return its next sequence number."""
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


def inspect_after_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
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

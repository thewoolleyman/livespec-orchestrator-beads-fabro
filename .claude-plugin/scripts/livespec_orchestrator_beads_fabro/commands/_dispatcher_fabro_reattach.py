"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import journal_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
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


_DEFAULT_TIMING = ReattachTiming()


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    follow_live: bool = False,
    timing: ReattachTiming = _DEFAULT_TIMING,
) -> FabroInspectResult | None:
    """Read a run, optionally supervising it after a lost client stream.

    Only confirmed terminal evidence ends supervision immediately. Failed or
    unrecognized reads use exponential backoff, capped at a minute, for at most
    ten minutes or twelve consecutive unanswered inspections. Inspect timeouts
    consume that same budget. Confirmed live reads reset it and keep polling.
    """
    if run_id is None:
        return None
    unanswered = 0
    deadline = timing.clock() + _REATTACH_WINDOW_SECONDS
    while True:
        timeout = (
            min(_FABRO_INSPECT_TIMEOUT_SECONDS, max(0.001, deadline - timing.clock()))
            if follow_live
            else _FABRO_INSPECT_TIMEOUT_SECONDS
        )
        inspect = fabro_port_for_plan(plan=plan, runner=runner).inspect(
            run_id=run_id,
            timeout_seconds=timeout,
        )
        journal_stage(
            journal=journal,
            plan=plan,
            stage="fabro-inspect",
            result=cast("CommandResult", inspect.command),
        )
        if not follow_live or (
            inspect.command.exit_code == 0 and inspect.status_kind in TERMINAL_STATUS_KINDS
        ):
            return inspect
        if inspect.command.exit_code == 0 and inspect.status_kind in _LIVE_STATUS_KINDS:
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

"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_outcome import (
    unobservable_run_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach_watch import (
    ReattachObservationInputs,
    ReattachTiming,
    observe_reattached_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_second_reads import (
    executed_candidate_attribution,
    terminal_events_attachment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
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


_DEFAULT_TIMING = ReattachTiming()


def run_wall_ledger(*, repo: Path) -> LedgerComments | None:
    """Resolve the budget ledger after the engine has finished importing."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
        run_wall_ledger as resolved_run_wall_ledger,
    )

    return resolved_run_wall_ledger(repo=repo)


def _run_wall_budget_watch(*, ledger: LedgerComments | None) -> RunWallBudgetWatch:
    """Load the watch lazily so reattach stays importable during engine setup."""
    watch_type = cast("type[RunWallBudgetWatch] | None", globals().get("RunWallBudgetWatch"))
    if watch_type is None:
        from livespec_orchestrator_beads_fabro.commands import (
            _dispatcher_run_wall_budget_watch as budget_watch_module,
        )

        watch_type = budget_watch_module.RunWallBudgetWatch
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
            inspect=observe_reattached_run(
                inputs=ReattachObservationInputs(
                    plan=plan,
                    runner=runner,
                    journal=journal,
                    run_id=run_id,
                    follow_live=follow_live,
                    timing=timing,
                    ledger_resolver=run_wall_ledger,
                    budget_factory=_run_wall_budget_watch,
                )
            ),
        ),
    )


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

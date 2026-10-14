"""Observe the bound server run after the foreground client disconnects."""

from __future__ import annotations

import time
from collections.abc import Callable
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
    "inspect_after_run",
    "inspect_run",
]

_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
    follow_live: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> FabroInspectResult | None:
    """Read and journal `fabro inspect --json` for a parsed run id."""
    if run_id is None:
        return None
    while True:
        inspect = fabro_port_for_plan(plan=plan, runner=runner).inspect(
            run_id=run_id,
            timeout_seconds=_FABRO_INSPECT_TIMEOUT_SECONDS,
        )
        journal_stage(
            journal=journal,
            plan=plan,
            stage="fabro-inspect",
            result=cast("CommandResult", inspect.command),
        )
        if not (
            follow_live
            and inspect.command.exit_code == 0
            and inspect.status_kind in {"running", "runnable", "pending", "queued"}
        ):
            return inspect
        sleep(30.0)


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
        sleep=sleep,
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

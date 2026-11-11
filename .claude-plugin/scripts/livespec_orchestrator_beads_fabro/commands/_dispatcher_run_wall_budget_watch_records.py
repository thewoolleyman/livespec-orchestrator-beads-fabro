"""Journal the continue and cancel records emitted by the budget watchdog."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RunWallBudgetContinuation,
    run_wall_budget_continued_record,
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_refs import (
    VerifiedPreservationRef,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import RunWallStart
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_progress import (
    RunWallProgress,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    FABRO_RM_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    executing_stage,
    last_publish_draft_publication,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_run_probe import (
    WatchdogRunReading,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "cancel_run_wall_budget",
    "journal_run_wall_budget_continuation",
]


def journal_run_wall_budget_continuation(
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    journal: JournalWriter,
    run_id: str,
    elapsed_seconds: float,
    progress: RunWallProgress,
) -> None:
    """Journal the capture or first completion that permits continuation."""
    journal.append(
        record=run_wall_budget_continued_record(
            continuation=RunWallBudgetContinuation(
                work_item_id=plan.work_item_id,
                dispatch_id=dispatch_id,
                run_id=run_id,
                factory=plan.fabro_factory_name,
                executing_stage=None,
                elapsed_seconds=elapsed_seconds,
                budget=plan.run_wall_budget,
                ceiling=plan.run_wall_ceiling,
                progress_window_seconds=max(plan.node_timeouts.configured.values(), default=0),
                progress=progress,
            )
        )
    )


def cancel_run_wall_budget(  # noqa: PLR0913 — independent dispatch, run, reading, and preservation facts.
    *,
    dispatch_id: str | None,
    plan: DispatchPlan,
    port: FabroPort,
    journal: JournalWriter,
    run_id: str,
    elapsed_seconds: float,
    start: RunWallStart,
    reading: WatchdogRunReading,
    pointer: str | None,
    verified_ref: VerifiedPreservationRef | None,
    export_failure: str,
) -> None:
    """Remove the run and journal the reading deliberately taken before removal."""
    rm = port.rm(run_id=run_id, timeout_seconds=FABRO_RM_TIMEOUT_SECONDS)
    journal.append(
        record={
            **run_wall_budget_exceeded_record(
                work_item_id=plan.work_item_id,
                dispatch_id=dispatch_id,
                run_id=run_id,
                factory=plan.fabro_factory_name,
                executing_stage=executing_stage(events_json=reading.events_json),
                publication=last_publish_draft_publication(
                    events_json=reading.events_json,
                    record_text=reading.record_text,
                ),
                elapsed_seconds=elapsed_seconds,
                budget=plan.run_wall_budget,
                ceiling=plan.run_wall_ceiling,
                start_source=start.source,
                bound_exceeded=(
                    "ceiling" if elapsed_seconds > plan.run_wall_ceiling.seconds else "budget"
                ),
                preserved_pointer=pointer,
                preserved_ref=None if verified_ref is None else verified_ref.ref,
                preserved_ref_commit=None if verified_ref is None else verified_ref.commit,
                export_failed_measurement=export_failure,
            ),
            "rm_exit_code": rm.command.exit_code,
        }
    )

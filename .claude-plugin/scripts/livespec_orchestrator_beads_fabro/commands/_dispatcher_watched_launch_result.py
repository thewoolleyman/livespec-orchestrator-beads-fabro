"""What a watched launch hands the engine once its watch loop has ended.

The watch loop ends one of four ways: a reaped run whose work-item stopped being
dispatchable, a run cancelled past its whole-run wall budget, a run cancelled as
stalled, or the run's own return. The first three end with a `fabro rm -f` the
launcher joins its run thread against; the last is simply joined. Mapping the
ending onto the `FabroRunResult` the engine reads is one concern, apart from
running and watching the run.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandResult,
    FabroRunResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_watch_decision import (
    RunWatchState,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel import (
    FABRO_RM_TIMEOUT_SECONDS,
)

__all__: list[str] = [
    "WatchResult",
    "watched_launch_result",
]

# The `fabro rm -f` budget lives with the cancel it belongs to
# (`_dispatcher_stall_cancel`); this module reads it back because it joins the
# run thread against the same number — the thread is waiting for the
# `fabro run` that `rm` is what ends, so two different budgets would let the
# join outlive or undercut the cancel it is waiting on.


@dataclass(frozen=True, kw_only=True)
class WatchResult:
    stalled_run_id: str | None = None
    budget_exceeded_run_id: str | None = None
    abandoned_run_id: str | None = None
    abandoned_item_status: str | None = None
    run_watch_state: RunWatchState | None = None


def watched_launch_result(
    *,
    watched: WatchResult,
    thread: threading.Thread,
    holder: dict[str, CommandResult],
    run_id_holder: dict[str, str | None],
) -> FabroRunResult:
    """The engine-facing result of one watched launch, joining its run thread."""
    if watched.abandoned_run_id is not None:
        thread.join(timeout=FABRO_RM_TIMEOUT_SECONDS)
        return FabroRunResult(
            command=holder.get(
                "result",
                CommandResult(exit_code=1, stdout="", stderr="cancelled by stale item reaper"),
            ),
            abandoned_run_id=watched.abandoned_run_id,
            abandoned_item_status=watched.abandoned_item_status,
        )
    if watched.budget_exceeded_run_id is not None:
        thread.join(timeout=FABRO_RM_TIMEOUT_SECONDS)
        return FabroRunResult(
            command=holder.get(
                "result",
                CommandResult(
                    exit_code=124, stdout="", stderr="cancelled on the whole-run wall budget"
                ),
            ),
            budget_exceeded_run_id=watched.budget_exceeded_run_id,
        )
    if watched.stalled_run_id is not None:
        thread.join(timeout=FABRO_RM_TIMEOUT_SECONDS)
        return FabroRunResult(
            command=holder.get(
                "result",
                CommandResult(exit_code=124, stdout="", stderr="cancelled by stall watchdog"),
            ),
            stalled_run_id=watched.stalled_run_id,
        )
    thread.join()
    return FabroRunResult(
        command=holder["result"],
        run_id=run_id_holder.get("run_id"),
        run_watch_state=watched.run_watch_state,
    )

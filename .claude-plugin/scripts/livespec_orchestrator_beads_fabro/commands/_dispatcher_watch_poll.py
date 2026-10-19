"""What ONE watchdog poll saw, as one reading the loop can act on.

Extracted from `_dispatcher_io_fabro_launcher` when the whole-run wall budget's
arm pushed that module past its size ceilings. The launcher keeps the loop and
the two cancel DECISIONS; this owns the step before them — taking the poll's
observation of the run and reporting what it implies.

THE SEAM IS WHERE IT IS BECAUSE OF WHAT IT GROUPS. Every field below is read
from the SAME observation, and each is read by a different arm of the loop: the
run itself binds the next poll's route, the running run id gates both cancels,
the abandoned status ends the dispatch, and the attribution rides to the next
poll. Returning them as one value is what keeps the loop from taking a second
reading for any one of them — the per-poll cost the bound-poll clause caps is
one `fabro inspect`, and a second read would also be a second answer nothing
announces the divergence between.

`running_run_id` IS DELIBERATELY NARROWER THAN `run`. A `runnable` run is
already this dispatch's run to OBSERVE — so it binds `bound_run_id` and every
later poll reads it by id — and is not yet one to CANCEL, because a queued run
holds no slot and has no progress to have stalled. Carrying both keeps that
distinction in the reading rather than in each arm's own condition.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import stamped_attribution
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    recorded_running_epoch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stale_item_reap import (
    stale_item_reap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_observation import (
    observed_run,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution

__all__: list[str] = [
    "WatchPoll",
    "observe_watch_poll",
]

_RUNNING_STATUS_KIND = "running"


@dataclass(frozen=True, kw_only=True)
class WatchPoll:
    """One poll's reading of the dispatched run.

    `run` is the run as this poll observed it, or None when the poll could not
    observe one at all. `running_run_id` is populated only where that reading
    found it RUNNING, which is the state both cancel arms are gated on.
    `recorded_running_epoch` is the instant the run's OWN record names for when
    it entered `running`, read from the same reading, or None when the record
    carries none — which is the whole-run wall budget's documented fallback to
    the first poll that observed the run running. `abandoned_item_status` is the
    status this run's work-item had left `active` for, non-None only where the
    run was reaped for it. `attribution` is the stamp carried to the next poll.
    """

    run: FabroRunSummary | None
    running_run_id: str | None
    recorded_running_epoch: float | None
    abandoned_item_status: str | None
    attribution: RunAttribution


def observe_watch_poll(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    port: FabroPort,
    attribution: RunAttribution,
    bound_run_id: str | None,
) -> WatchPoll:
    """Take this poll's observation, reaping the run if its item moved on.

    The REAP is taken here rather than left to the loop because it is part of
    the reading: whether this run is still this dispatch's to watch is answered
    by the same poll that answered where the run is, and a loop that asked
    separately could act on a run the ledger had already finished with.

    It is attempted only where the poll OBSERVED the run, for the reason the
    bound-poll clause gives about unobservable reads: a poll that saw nothing
    has established nothing about the run, and reaping on it would destroy
    healthy work on the strength of a failed probe.
    """
    observed = observed_run(
        work_item_id=plan.work_item_id,
        port=port,
        journal=journal,
        attribution=attribution,
        bound_run_id=bound_run_id,
    )
    run = observed.run
    # THE STAMP PRECEDES THE REAP, and the order is the original loop's rather
    # than an artifact of how this value is built. The dispatch-run stamp is
    # what lets anyone reconciling the factory attribute this run to this item,
    # and it is written while the run is still alive; a reap taken first would
    # skip it for exactly the runs whose attribution is hardest to recover
    # afterwards, because the run is about to be destroyed.
    stamp = stamped_attribution(plan=plan, journal=journal, run=run, attribution=attribution)
    return WatchPoll(
        run=run,
        recorded_running_epoch=recorded_running_epoch(payload=observed.record),
        running_run_id=(
            run.run_id if run is not None and run.status_kind == _RUNNING_STATUS_KIND else None
        ),
        abandoned_item_status=(
            None
            if run is None
            else stale_item_reap(plan=plan, runner=runner, journal=journal, run_id=run.run_id)
        ),
        attribution=stamp,
    )

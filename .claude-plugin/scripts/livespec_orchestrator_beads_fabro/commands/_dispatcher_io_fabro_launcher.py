"""Fabro launcher side-effect seam for the Dispatcher."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    dispatch_correlation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
    dispatch_fabro_run_inputs,
    run_fabro_factory_auth_login,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    LivenessState,
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import (
    release_pass_snapshot,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCheckpoint,
    ignore_prelaunch_checkpoint,
    prelaunch_phase,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import (
    dispatch_run_label_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_preserve import (
    run_wall_ledger,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallBudgetWatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_watch_decision import (
    decide_run_watch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watch_poll import (
    WatchPollBinding,
    observe_watch_poll,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watched_launch_result import (
    WatchResult,
    watched_launch_result,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    fabro_port_for_plan,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution

__all__: list[str] = ["WatchedFabroLauncher"]

# The `fabro run` subprocess ceiling rides on `plan.fabro_timeout_seconds`,
# derived per dispatch from the resolved node timeouts and stall timeout
# (`_node_timeouts.derive_fabro_timeout_seconds`) — the watched and
# synchronous launchers deliberately read the SAME number, so a repository
# that lengthens a node cannot have one path outlive the other.
_WATCHDOG_POLL_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class WatchedFabroLauncher:
    """Production FabroLauncher: `fabro run` + the coarse wall-clock watchdog."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    # The WALL clock the whole-run wall budget is measured on, separate from
    # `clock` above because the two answer different questions. The liveness
    # samples compare spans WITHIN one process, which is what `monotonic` is
    # for; the budget's start instant can come from the FACTORY'S OWN RECORD of
    # when the run began running, which is a wall-clock instant, so the two
    # cannot be measured against one reading.
    wall_clock: Callable[[], float] = time.time
    heartbeat_path: Path | None = None
    # The dispatch id this launch was minted under — the id
    # `cc_otel_overlay_env` projects into the sandbox and therefore the id
    # the heartbeat sink keys every beat by. It rides the launcher beside
    # `heartbeat_path` because both are per-dispatch wiring for the SAME
    # probe; None means the caller supplied none, and the probe falls back
    # to the work-item id alone.
    dispatch_id: str | None = None
    # The native-secret launch transaction is released only once the candidate
    # worker reports RUNNING. Its worker records that transition after loading
    # and snapshotting the vault; RUNNABLE is only queue admission and is too
    # early. None keeps every non-native caller on the old path.
    on_worker_running: Callable[[], None] | None = None
    # A run-only source venue; watchdog and auth commands retain the ordinary runner.
    run_runner: CommandRunner | None = None
    # Receives the name of each launch-side phase as it ends, so the drive's
    # pre-launch CPU profile covers the phases that run inside the launch too.
    prelaunch_checkpoint: PrelaunchCheckpoint = ignore_prelaunch_checkpoint

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        with prelaunch_phase(checkpoint=self.prelaunch_checkpoint, name="launch-factory-auth"):
            run_fabro_factory_auth_login(plan=plan, runner=runner)
        with prelaunch_phase(checkpoint=self.prelaunch_checkpoint, name="fabro-port"):
            port = fabro_port_for_plan(plan=plan, runner=runner)
        with prelaunch_phase(checkpoint=self.prelaunch_checkpoint, name="release-pass-snapshot"):
            release_pass_snapshot()
        holder: dict[str, CommandResult] = {}
        run_id_holder: dict[str, str | None] = {}
        # Set once this dispatch's `fabro run` call has RETURNED, which is
        # what the watch loop reads as the run being OVER. A thread that has
        # not yet exited is NOT a run still running: `fabro run` returns from
        # inside the thread and the interpreter tears that thread down
        # afterwards, a lag that widens under load. Keyed on `is_alive` alone,
        # a poll resumed after the run had already finished, sampled a run
        # that was over, and cancelled it — the event stream freezes when a
        # run ends, so that sample reads exactly like a stall (bd-ib-qhyxqs,
        # measured in the sandbox of run 01M4WWQNRN2J at hp load about 23).
        run_returned = threading.Event()

        def _run_fabro() -> None:
            result = port.run(
                runner=self.run_runner,
                workflow_toml=plan.workflow_toml,
                goal_file=plan.goal_file,
                inputs=dispatch_fabro_run_inputs(plan=plan),
                timeout_seconds=plan.fabro_timeout_seconds,
                # The repository and each ACP node's rendered candidate
                # entitlement, so this run's own record carries the attempt
                # identity section "Factory-configurable ACP fallback
                # priority" requires to be discoverable host-wide. Read off
                # the PLAN rather than re-resolved here, for the reason the
                # adapters themselves are: the resolution is what the
                # dispatch record journaled, and re-deriving it at launch is
                # how the record and the run come to disagree.
                labels=dispatch_run_label_pairs(repo=plan.repo, acp_nodes=plan.acp_nodes),
                # The dispatch id this launch was minted under, so the
                # engine's run spans carry the SAME triple the dispatch
                # span does. Read off the launcher rather than re-derived:
                # the heartbeat sink already keys every beat by this field,
                # and a second id here would correlate the trace to a
                # dispatch the journal never recorded.
                correlation=dispatch_correlation(
                    work_item_id=plan.work_item_id,
                    dispatch_id=self.dispatch_id,
                    factory=plan.fabro_factory_name,
                ),
            )
            holder["result"] = cast("CommandResult", result.command)
            run_id_holder["run_id"] = result.run_id
            # Last, so that anything which observes the signal and then joins
            # this thread finds the result already published.
            run_returned.set()

        thread = threading.Thread(target=_run_fabro, name=f"fabro-run-{plan.work_item_id}")
        thread.daemon = True
        thread.start()
        watched = self._watch(
            plan=plan,
            runner=runner,
            journal=journal,
            thread=thread,
            run_returned=run_returned,
            port=port,
        )
        return watched_launch_result(
            watched=watched, thread=thread, holder=holder, run_id_holder=run_id_holder
        )

    def _watch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        thread: threading.Thread,
        run_returned: threading.Event,
        port: FabroPort,
    ) -> WatchResult:
        # The window this run is graded against comes from the plan, which
        # resolved `dispatcher.stall_timeout_seconds` through the node timeouts'
        # own layers once per dispatch. Reading it here rather than resolving a
        # second time is what keeps it in step with the `stall_timeout` written
        # into the rendered graph and with the subprocess ceiling derived from
        # the same number.
        stall_seconds = plan.stall_window.seconds
        samples: list[LivenessSample] = []
        liveness_state = LivenessState()
        known_run_id: str | None = None
        # The run this watch loop has BOUND, and so the one every poll after
        # the first match reads BY ID rather than hunting for in a listing.
        # Deliberately NOT `known_run_id`, which is the narrower "has this run
        # ever been seen RUNNING" the stall cancel is gated on: a `runnable`
        # run is already this dispatch's run to observe, and is not yet one to
        # cancel.
        bound_run_id: str | None = None
        worker_running_notified = False
        # This run's budget clock and the ledger its export writes through. It
        # holds the clock rather than this loop, so the fix-it-once rule has
        # exactly one home; see `RunWallBudgetWatch`.
        budget = RunWallBudgetWatch(ledger=run_wall_ledger(repo=plan.repo))
        stamp = RunAttribution()
        # The run's own RETURN ends the watch. The thread's death is consulted
        # beside it only because `port.run` can RAISE: no signal arrives on
        # that path, and a loop watching the signal alone would then poll a
        # dead thread for the rest of the dispatch.
        while not run_returned.is_set() and thread.is_alive():
            self.sleep(_WATCHDOG_POLL_INTERVAL_SECONDS)
            if run_returned.is_set() or not thread.is_alive():
                # The run ended during the sleep, so NO liveness sample is
                # taken of it: its event stream froze when it ended, and a
                # sample taken after that reads as a stall and cancels work
                # that had already completed. A run whose `fabro run` has NOT
                # returned, and whose liveness stays flat for the full stall
                # window, is still cancelled as stalled-no-progress below.
                return WatchResult()
            poll = observe_watch_poll(
                plan=plan,
                runner=runner,
                journal=journal,
                port=port,
                binding=WatchPollBinding(
                    attribution=stamp,
                    bound_run_id=bound_run_id,
                    dispatch_id=self.dispatch_id,
                ),
            )
            stamp = poll.attribution
            run, run_id = poll.run, poll.running_run_id
            known_run_id = run_id if run_id is not None else known_run_id
            bound_run_id = run.run_id if run is not None else bound_run_id
            if poll.abandoned_item_status is not None and run is not None:
                return WatchResult(
                    abandoned_run_id=run.run_id,
                    abandoned_item_status=poll.abandoned_item_status,
                )
            if run_id is not None and not worker_running_notified:
                self._notify_worker_running()
                worker_running_notified = True
            liveness_state.observe_run(record=poll.record, journal=journal)
            samples.append(
                liveness_sample(
                    plan=plan,
                    port=port,
                    run_id=bound_run_id or run_id,
                    heartbeat_path=self.heartbeat_path,
                    dispatch_id=self.dispatch_id,
                    observed_at=self.clock(),
                    state=liveness_state,
                )
            )
            if known_run_id is None or run is None or run.status_kind != "running":
                continue
            decision = decide_run_watch(
                budget=budget,
                dispatch_id=self.dispatch_id,
                plan=plan,
                port=port,
                runner=runner,
                journal=journal,
                run_id=known_run_id,
                recorded_epoch=poll.recorded_running_epoch,
                now_epoch=self.wall_clock(),
                samples=tuple(samples),
                stall_seconds=stall_seconds,
            )
            if decision.budget_exceeded:
                return WatchResult(budget_exceeded_run_id=known_run_id)
            if decision.stalled:
                return WatchResult(stalled_run_id=known_run_id)
        return WatchResult()

    def _notify_worker_running(self) -> None:
        """Release the native-secret launch transaction, if one is wired.

        A method rather than a nested branch in the loop for the reason the
        stale-item reap moved out: the loop's job is to decide, and a caller
        with no transaction to release is not a decision.
        """
        if self.on_worker_running is not None:
            self.on_worker_running()

"""Fabro launcher side-effect seam for the Dispatcher."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
    dispatch_fabro_run_inputs,
    run_fabro_factory_auth_login,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    FABRO_PROBE_TIMEOUT_SECONDS,
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import stamped_attribution
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    quiet_window_seconds,
    resolve_stall_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_discovery import (
    journaled_discovery,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    FabroRunSummary,
    fabro_port_for_plan,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import read_work_items

__all__: list[str] = ["WatchedFabroLauncher"]

# The `fabro run` subprocess ceiling rides on `plan.fabro_timeout_seconds`,
# derived per dispatch from the resolved node timeouts and stall timeout
# (`_node_timeouts.derive_fabro_timeout_seconds`) — the watched and
# synchronous launchers deliberately read the SAME number, so a repository
# that lengthens a node cannot have one path outlive the other.
_FABRO_RM_TIMEOUT_SECONDS = 120.0
_WATCHDOG_POLL_INTERVAL_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class _WatchResult:
    stalled_run_id: str | None = None
    abandoned_run_id: str | None = None
    abandoned_item_status: str | None = None


@dataclass(frozen=True, kw_only=True)
class WatchedFabroLauncher:
    """Production FabroLauncher: `fabro run` + the coarse wall-clock watchdog."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
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

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        run_fabro_factory_auth_login(plan=plan, runner=runner)
        port = fabro_port_for_plan(plan=plan, runner=runner)
        holder: dict[str, CommandResult] = {}
        run_id_holder: dict[str, str | None] = {}

        def _run_fabro() -> None:
            result = port.run(
                workflow_toml=plan.workflow_toml,
                goal_file=plan.goal_file,
                inputs=dispatch_fabro_run_inputs(plan=plan),
                timeout_seconds=plan.fabro_timeout_seconds,
            )
            holder["result"] = cast("CommandResult", result.command)
            run_id_holder["run_id"] = result.run_id

        thread = threading.Thread(target=_run_fabro, name=f"fabro-run-{plan.work_item_id}")
        thread.daemon = True
        thread.start()
        watched = self._watch(plan=plan, runner=runner, journal=journal, thread=thread, port=port)
        if watched.abandoned_run_id is not None:
            thread.join(timeout=_FABRO_RM_TIMEOUT_SECONDS)
            return FabroRunResult(
                command=holder.get(
                    "result",
                    CommandResult(exit_code=1, stdout="", stderr="cancelled by stale item reaper"),
                ),
                abandoned_run_id=watched.abandoned_run_id,
                abandoned_item_status=watched.abandoned_item_status,
            )
        if watched.stalled_run_id is not None:
            thread.join(timeout=_FABRO_RM_TIMEOUT_SECONDS)
            return FabroRunResult(
                command=holder.get(
                    "result",
                    CommandResult(exit_code=124, stdout="", stderr="cancelled by stall watchdog"),
                ),
                stalled_run_id=watched.stalled_run_id,
            )
        thread.join()
        return FabroRunResult(command=holder["result"], run_id=run_id_holder.get("run_id"))

    def _watch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        thread: threading.Thread,
        port: FabroPort,
    ) -> _WatchResult:
        stall_seconds = resolve_stall_seconds()
        samples: list[LivenessSample] = []
        known_run_id: str | None = None
        worker_running_notified = False
        stamp = RunAttribution()
        while thread.is_alive():
            self.sleep(_WATCHDOG_POLL_INTERVAL_SECONDS)
            if not thread.is_alive():
                return _WatchResult()
            run = self._discover_run(plan=plan, port=port, journal=journal, attribution=stamp)
            stamp = stamped_attribution(plan=plan, journal=journal, run=run, attribution=stamp)
            run_id = run.run_id if run is not None and run.status_kind == "running" else None
            known_run_id = run_id if run_id is not None else known_run_id
            if run_id is not None and not worker_running_notified:
                if self.on_worker_running is not None:
                    self.on_worker_running()
                worker_running_notified = True
            if run is not None:
                item_status = _work_item_status(repo=plan.repo, work_item_id=plan.work_item_id)
                if item_status is not None and item_status != "active":
                    self._reap_stale_run(
                        plan=plan,
                        runner=runner,
                        journal=journal,
                        run_id=run.run_id,
                        item_status=item_status,
                    )
                    return _WatchResult(
                        abandoned_run_id=run.run_id,
                        abandoned_item_status=item_status,
                    )
            samples.append(
                liveness_sample(
                    plan=plan,
                    port=port,
                    run_id=run_id,
                    heartbeat_path=self.heartbeat_path,
                    dispatch_id=self.dispatch_id,
                    observed_at=self.clock(),
                )
            )
            if known_run_id is None or run is None or run.status_kind != "running":
                continue
            window = tuple(samples)
            if decide_stall(samples=window, stall_seconds=stall_seconds) == StallVerdict.STALLED:
                self._cancel(
                    plan=plan,
                    port=port,
                    journal=journal,
                    run_id=known_run_id,
                    stall_seconds=stall_seconds,
                    quiet_seconds=quiet_window_seconds(samples=window),
                )
                return _WatchResult(stalled_run_id=known_run_id)
        return _WatchResult()

    def _discover_run(
        self,
        *,
        plan: DispatchPlan,
        port: FabroPort,
        journal: JournalWriter,
        attribution: RunAttribution,
    ) -> FabroRunSummary | None:
        """Probe `fabro ps` and hand the poll to the journaling discovery seam.

        This method owns the port call and NOTHING else. The classification
        and its unconditional per-poll journal record live together in
        `_dispatcher_watchdog_discovery`, so no future caller can take the
        discovery result without leaving the record — the silent-miss shape
        that hid a total watchdog outage on `hp` for 11 days.

        `attribution` accumulates across the watch loop: it is empty on the
        first poll, so that poll matches on the goal-text regex, and carries the
        ledger stamp on every poll after, so a goal the regex later fails to
        parse can no longer blind the watchdog to its own run.
        """
        return journaled_discovery(
            work_item_id=plan.work_item_id,
            ps=port.ps(timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS),
            journal=journal,
            attribution=attribution,
        )

    def _cancel(
        self,
        *,
        plan: DispatchPlan,
        port: FabroPort,
        journal: JournalWriter,
        run_id: str,
        stall_seconds: float,
        quiet_seconds: float | None,
    ) -> None:
        """`fabro rm -f` the stalled run and journal what governed the decision.

        `stall_seconds` is the resolved stall interval and `quiet_seconds`
        is the window actually confirmed against it. Both ride the record
        because the interval alone cannot be checked — it says what the
        threshold was, never that anything reached it — and the 2026-10-09
        incident (bd-ib-n44n4e) had to be reconstructed from the run's own
        event stream because the record carried neither figure.
        """
        rm = port.rm(
            run_id=run_id,
            timeout_seconds=_FABRO_RM_TIMEOUT_SECONDS,
        )
        journal.append(
            record={
                "work_item_id": plan.work_item_id,
                "stage": "watchdog-stall-cancel",
                "run_id": run_id,
                "rm_exit_code": rm.command.exit_code,
                "stall_seconds": stall_seconds,
                "quiet_seconds": quiet_seconds,
            }
        )

    def _reap_stale_run(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        run_id: str,
        item_status: str,
    ) -> None:
        rm = fabro_port_for_plan(plan=plan, runner=runner).rm(
            run_id=run_id,
            timeout_seconds=_FABRO_RM_TIMEOUT_SECONDS,
        )
        journal.append(
            record={
                "work_item_id": plan.work_item_id,
                "stage": "stale-run-reap",
                "run_id": run_id,
                "item_status": item_status,
                "rm_exit_code": rm.command.exit_code,
            }
        )


def _work_item_status(*, repo: Path, work_item_id: str) -> str | None:
    config = store_config(repo=repo) if (repo / ".livespec.jsonc").is_file() else None
    if config is None:
        return None
    try:
        items = read_work_items(path=config)
    except (BeadsCommandError, BeadsConnectionError):
        return None
    for item in items:
        if item.id == work_item_id:
            return item.status
    return None

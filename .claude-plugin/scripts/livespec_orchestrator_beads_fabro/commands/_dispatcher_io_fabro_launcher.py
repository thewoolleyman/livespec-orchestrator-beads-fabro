"""Fabro launcher side-effect seam for the Dispatcher."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    fabro_events_argv,
    fabro_inspect_argv,
    fabro_ps_argv,
    fabro_rm_argv,
    fabro_run_argv,
    parse_running_run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    parse_last_event_epoch,
    resolve_stall_seconds,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink

__all__: list[str] = ["WatchedFabroLauncher"]

_FABRO_TIMEOUT_SECONDS = 54000.0
_FABRO_PROBE_TIMEOUT_SECONDS = 60.0
_FABRO_RM_TIMEOUT_SECONDS = 120.0
_WATCHDOG_POLL_INTERVAL_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class _WallClockEventProbe:
    """The coarse wall-clock backstop expressed as a liveness probe."""

    plan: DispatchPlan
    runner: CommandRunner
    run_id: str | None

    def sample(self, *, observed_at: float) -> LivenessSample:
        if self.run_id is None:
            return LivenessSample(last_event_epoch=None, observed_at=observed_at)
        events = self.runner.run(
            argv=fabro_events_argv(plan=self.plan, run_id=self.run_id),
            cwd=self.plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        inspect = self.runner.run(
            argv=fabro_inspect_argv(plan=self.plan, run_id=self.run_id),
            cwd=self.plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        events_json = events.stdout if events.exit_code == 0 else ""
        inspect_json = inspect.stdout if inspect.exit_code == 0 else ""
        epoch = parse_last_event_epoch(events_json=events_json, inspect_json=inspect_json)
        return LivenessSample(last_event_epoch=epoch, observed_at=observed_at)


@dataclass(frozen=True, kw_only=True)
class WatchedFabroLauncher:
    """Production FabroLauncher: `fabro run` + the coarse wall-clock watchdog."""

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    heartbeat_path: Path | None = None

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        holder: dict[str, CommandResult] = {}

        def _run_fabro() -> None:
            holder["result"] = runner.run(
                argv=fabro_run_argv(plan=plan),
                cwd=plan.repo,
                timeout_seconds=_FABRO_TIMEOUT_SECONDS,
            )

        thread = threading.Thread(target=_run_fabro, name=f"fabro-run-{plan.work_item_id}")
        thread.daemon = True
        thread.start()
        stalled_run_id = self._watch(plan=plan, runner=runner, journal=journal, thread=thread)
        if stalled_run_id is not None:
            thread.join(timeout=_FABRO_RM_TIMEOUT_SECONDS)
            return FabroRunResult(
                command=holder.get(
                    "result",
                    CommandResult(exit_code=124, stdout="", stderr="cancelled by stall watchdog"),
                ),
                stalled_run_id=stalled_run_id,
            )
        thread.join()
        return FabroRunResult(command=holder["result"])

    def _watch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        thread: threading.Thread,
    ) -> str | None:
        stall_seconds = resolve_stall_seconds()
        samples: list[LivenessSample] = []
        known_run_id: str | None = None
        while thread.is_alive():
            self.sleep(_WATCHDOG_POLL_INTERVAL_SECONDS)
            if not thread.is_alive():
                return None
            run_id = self._discover_run_id(plan=plan, runner=runner)
            known_run_id = run_id if run_id is not None else known_run_id
            samples.append(self._sample(plan=plan, runner=runner, run_id=run_id))
            if known_run_id is None:
                continue
            if decide_stall(samples=tuple(samples), stall_seconds=stall_seconds) == (
                StallVerdict.STALLED
            ):
                self._cancel(plan=plan, runner=runner, journal=journal, run_id=known_run_id)
                return known_run_id
        return None

    def _discover_run_id(self, *, plan: DispatchPlan, runner: CommandRunner) -> str | None:
        ps = runner.run(
            argv=fabro_ps_argv(plan=plan),
            cwd=plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        if ps.exit_code != 0:
            return None
        return parse_running_run_id(ps_json=ps.stdout, work_item_id=plan.work_item_id)

    def _sample(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        run_id: str | None,
    ) -> LivenessSample:
        observed_at = self.clock()
        wall_clock = _WallClockEventProbe(plan=plan, runner=runner, run_id=run_id)
        if self.heartbeat_path is None:
            return wall_clock.sample(observed_at=observed_at)
        heartbeat = HeartbeatLivenessProbe(
            sink=HeartbeatSink(path=self.heartbeat_path),
            keys=heartbeat_lookup_keys(work_item_id=plan.work_item_id, run_id=run_id),
        )
        layered = LayeredLivenessProbe(primary=heartbeat, fallback=wall_clock)
        return layered.sample(observed_at=observed_at)

    def _cancel(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        run_id: str,
    ) -> None:
        rm = runner.run(
            argv=fabro_rm_argv(plan=plan, run_id=run_id),
            cwd=plan.repo,
            timeout_seconds=_FABRO_RM_TIMEOUT_SECONDS,
        )
        journal.append(
            record={
                "work_item_id": plan.work_item_id,
                "stage": "watchdog-stall-cancel",
                "run_id": run_id,
                "rm_exit_code": rm.exit_code,
            }
        )

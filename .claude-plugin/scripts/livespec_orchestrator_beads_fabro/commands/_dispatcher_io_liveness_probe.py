"""Liveness-probe assembly for the Dispatcher's in-flight watch loop.

One concern: given a poll's discovered run id, produce the ONE
`LivenessSample` the watchdog decision is fed. That means owning the
coarse wall-clock event probe and the layering of the finer heartbeat
primary over it — which is a different job from the thread and
`fabro ps` orchestration in `_dispatcher_io_fabro_launcher`, the module
this was cut out of.

The layering direction is load-bearing: the heartbeat is the PRIMARY and
the wall-clock event stream is the FALLBACK, so a heartbeat-pipeline
outage degrades the watchdog to coarse detection rather than to NO
detection. A dispatch that wires no heartbeat path reaches the
wall-clock probe directly, which is what keeps the backstop a backstop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    parse_last_event_epoch,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink

__all__: list[str] = [
    "FABRO_PROBE_TIMEOUT_SECONDS",
    "liveness_sample",
]

# Budget for ONE read-only `fabro` probe the watch loop issues — the
# `fabro events` call below and the `fabro ps` discovery call in the
# launcher. One constant rather than one per verb: they are the same kind
# of call against the same factory, and two numbers here would read as a
# pair that must be kept in step.
FABRO_PROBE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _WallClockEventProbe:
    """The coarse wall-clock backstop expressed as a liveness probe."""

    plan: DispatchPlan
    port: FabroPort
    run_id: str | None

    def sample(self, *, observed_at: float) -> LivenessSample:
        if self.run_id is None:
            return LivenessSample(last_event_epoch=None, observed_at=observed_at)
        # `fabro events` is the SOLE source: the `fabro inspect` /
        # `updated_at` fallback this probe used to also read is removed
        # (bd-ib-tec5sz — the pinned build never emits that field). Not
        # probing inspect at all is what keeps a `fabro events` outage a
        # "no signal", rather than a node-resolution clock that would
        # read a healthy long node as a stall.
        events = self.port.events(
            run_id=self.run_id,
            timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS,
        )
        events_json = events.command.stdout if events.command.exit_code == 0 else ""
        epoch = parse_last_event_epoch(events_json=events_json)
        return LivenessSample(last_event_epoch=epoch, observed_at=observed_at)


def liveness_sample(
    *,
    plan: DispatchPlan,
    port: FabroPort,
    run_id: str | None,
    heartbeat_path: Path | None,
    dispatch_id: str | None,
    observed_at: float,
) -> LivenessSample:
    """Take the one liveness observation this poll contributes to the decision.

    `heartbeat_path` None means the dispatch wired no heartbeat sink, so
    the coarse wall-clock probe answers alone; otherwise the heartbeat
    primary answers and falls back to it. `dispatch_id` is the id the
    overlay projected into the sandbox and therefore the id the sink keys
    every beat by; None falls back to the work-item id alone.
    """
    wall_clock = _WallClockEventProbe(plan=plan, port=port, run_id=run_id)
    if heartbeat_path is None:
        return wall_clock.sample(observed_at=observed_at)
    heartbeat = HeartbeatLivenessProbe(
        sink=HeartbeatSink(path=heartbeat_path),
        keys=heartbeat_lookup_keys(work_item_id=plan.work_item_id, dispatch_id=dispatch_id),
    )
    layered = LayeredLivenessProbe(primary=heartbeat, fallback=wall_clock)
    return layered.sample(observed_at=observed_at)

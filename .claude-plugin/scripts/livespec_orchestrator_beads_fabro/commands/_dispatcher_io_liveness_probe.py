"""Liveness-probe assembly for the Dispatcher's in-flight watch loop.

One concern: given a poll's discovered run id, produce the ONE
`LivenessSample` the watchdog decision is fed. That means owning the
coarse wall-clock event probe and the layering of the finer heartbeat
primary over it — which is a different job from the thread and
`fabro ps` orchestration in `_dispatcher_io_fabro_launcher`, the module
this was cut out of.

The layering is load-bearing: the heartbeat is the FINER layer and the
wall-clock event stream is the PERMANENT backstop, and the composition
reports whichever is NEWER, so a heartbeat-pipeline outage degrades the
watchdog to coarse detection rather than to NO detection and a frozen
heartbeat never masks an advancing event stream (bd-ib-qsk4o5). A dispatch
that wires no heartbeat path reaches the wall-clock probe directly, which
is what keeps the backstop a backstop.

The open-command-node observation is read HERE, from the same `fabro
events` output the wall-clock reading is parsed from, rather than by a
second probe. One read answers both questions, so the two can never
disagree about the stream they describe — and a second read would double
the per-poll probe cost on every dispatch in the fleet.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_open_command_node import (
    updated_open_command_node,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    OpenCommandNode,
    parse_last_event_epoch,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.commands._fabro_record_instant import (
    record_instant_epoch,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink

__all__: list[str] = [
    "FABRO_PROBE_TIMEOUT_SECONDS",
    "STREAM_POLL_JOURNAL_STAGE",
    "LivenessState",
    "liveness_sample",
]

# Budget for ONE read-only `fabro` probe the watch loop issues — the
# `fabro events` call below, and the `fabro ps` / `fabro inspect` run
# observations in `_dispatcher_watchdog_observation`. One constant rather
# than one per verb: they are the same kind of call against the same
# factory, and three numbers here would read as a set that must be kept in
# step.
FABRO_PROBE_TIMEOUT_SECONDS = 60.0
STREAM_POLL_JOURNAL_STAGE = "watchdog-stream-poll"


@dataclass(kw_only=True)
class LivenessState:
    """The event facts one watch has established for its bound run."""

    newest_event_epoch: float | None = None
    open_command_node: OpenCommandNode | None = None
    stream_seq: int | None = None
    run_record: object | None = None
    journal: JournalWriter | None = None

    def observe_run(self, *, record: object | None, journal: JournalWriter) -> None:
        """Carry this poll's by-id record and journal into its liveness read."""
        self.run_record = record
        self.journal = journal


@dataclass(frozen=True, kw_only=True)
class _WallClockEventProbe:
    """The coarse wall-clock backstop expressed as a liveness probe."""

    plan: DispatchPlan
    port: FabroPort
    run_id: str | None
    state: LivenessState

    def sample(self, *, observed_at: float) -> LivenessSample:
        if self.run_id is None:
            return LivenessSample(last_event_epoch=None, observed_at=observed_at)
        records, observable, status = self._read_event_pages(run_id=self.run_id)
        stage_epoch = _stage_progress_epoch(record=self.state.run_record)
        if self.state.journal is not None:
            self.state.journal.append(
                record={
                    "stage": STREAM_POLL_JOURNAL_STAGE,
                    "run_id": self.run_id,
                    "observable": observable,
                    "status": status,
                    **({} if observable else {"reason": "stream-read-unobservable"}),
                }
            )
        if not observable:
            return _stage_progress_sample(
                state=self.state,
                stage_epoch=stage_epoch,
                observed_at=observed_at,
            )
        events_json = json.dumps(records)
        newest = parse_last_event_epoch(events_json=events_json)
        progress = max(
            (epoch for epoch in (newest, stage_epoch) if epoch is not None), default=None
        )
        self.state.open_command_node = updated_open_command_node(
            established=self.state.open_command_node,
            events_json=events_json,
            timeouts=self.plan.node_timeouts,
        )
        if progress is not None and (
            self.state.newest_event_epoch is None or progress > self.state.newest_event_epoch
        ):
            self.state.newest_event_epoch = progress
        return LivenessSample(
            last_event_epoch=self.state.newest_event_epoch,
            observed_at=observed_at,
            # Read from the SAME output as the timestamp above, against this
            # dispatch's own resolved node timeouts, so the bound the stall
            # decision applies is the value the rendered graph gave the node.
            open_command_node=self.state.open_command_node,
        )

    def _read_event_pages(self, *, run_id: str) -> tuple[tuple[dict[str, object], ...], bool, int]:
        """Read every available server page within this poll's one read budget.

        A completed empty page is a successful observation: it says the bound
        run emitted nothing after its cursor, rather than saying the watchdog
        failed to observe the run.  A later page failure does not discard an
        earlier page's cursor; the next poll resumes immediately after the
        newest stream sequence actually received.
        """
        deadline = time.monotonic() + FABRO_PROBE_TIMEOUT_SECONDS
        records: tuple[dict[str, object], ...] = ()
        status = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return records, False, status
            stream = self.port.server_api().stream(
                run_id=run_id,
                after=self.state.stream_seq,
                timeout_seconds=remaining,
            )
            status = stream.status
            if not stream.succeeded:
                return records, False, status
            page = fabro_event_records_from_stdout(stdout=stream.body)
            if page is None:
                return records, False, status
            records += page
            previous_cursor = self.state.stream_seq
            self.state.stream_seq = _newest_stream_seq(records=page, current=previous_cursor)
            if not _page_has_more(payload=stream.payload):
                return records, True, status
            if self.state.stream_seq == previous_cursor:
                return records, False, status


def _page_has_more(*, payload: object | None) -> bool:
    """Whether a successful event-page response declares another page."""
    if not isinstance(payload, Mapping):
        return False
    payload_mapping = cast("Mapping[str, object]", payload)
    meta: object = payload_mapping.get("meta")
    return isinstance(meta, Mapping) and cast("Mapping[str, object]", meta).get("has_more") is True


def liveness_sample(  # noqa: PLR0913 — each poll input names an independent dispatch or probe fact.
    *,
    plan: DispatchPlan,
    port: FabroPort,
    run_id: str | None,
    heartbeat_path: Path | None,
    dispatch_id: str | None,
    observed_at: float,
    state: LivenessState,
    run_record: object | None = None,
    journal: JournalWriter | None = None,
) -> LivenessSample:
    """Take the one liveness observation this poll contributes to the decision.

    `heartbeat_path` None means the dispatch wired no heartbeat sink, so
    the coarse wall-clock probe answers alone; otherwise the heartbeat
    primary answers and falls back to it. `dispatch_id` is the id the
    overlay projected into the sandbox and therefore the id the sink keys
    every beat by; None falls back to the work-item id alone.
    """
    wall_clock = _WallClockEventProbe(
        plan=plan,
        port=port,
        run_id=run_id,
        state=state,
    )
    if run_record is not None:
        state.run_record = run_record
    if journal is not None:
        state.journal = journal
    if heartbeat_path is None:
        return wall_clock.sample(observed_at=observed_at)
    heartbeat = HeartbeatLivenessProbe(
        sink=HeartbeatSink(path=heartbeat_path),
        keys=heartbeat_lookup_keys(work_item_id=plan.work_item_id, dispatch_id=dispatch_id),
    )
    layered = LayeredLivenessProbe(primary=heartbeat, fallback=wall_clock)
    return layered.sample(observed_at=observed_at)


def _newest_stream_seq(
    *, records: tuple[dict[str, object], ...], current: int | None
) -> int | None:
    """Advance the cursor only from a real server-issued stream sequence."""
    sequences = [
        value
        for record in records
        if isinstance(value := record.get("stream_seq"), int) and not isinstance(value, bool)
    ]
    if not sequences:
        return current
    return max((*sequences, current)) if current is not None else max(sequences)


def _stage_progress_sample(
    *, state: LivenessState, stage_epoch: float | None, observed_at: float
) -> LivenessSample:
    """Use a newer by-id stage transition; otherwise keep a failed stream unobservable."""
    if stage_epoch is not None and (
        state.newest_event_epoch is None or stage_epoch > state.newest_event_epoch
    ):
        state.newest_event_epoch = stage_epoch
        return LivenessSample(last_event_epoch=stage_epoch, observed_at=observed_at)
    return LivenessSample(last_event_epoch=None, observed_at=observed_at)


def _stage_progress_epoch(*, record: object | None) -> float | None:
    """Newest stage transition instant the bound run's status record names."""
    inspected = fabro_inspect_record(payload=record)
    if inspected is None:
        return None
    instants = _stage_instants(value=inspected.get("stages")) + _stage_instants(
        value=inspected.get("status")
    )
    return max(instants) if instants else None


def _stage_instants(*, value: object) -> list[float]:
    if not isinstance(value, Mapping):
        return []
    instants: list[float] = []
    stages = cast("Mapping[str, object]", value)
    for key in ("started_at_epoch", "finished_at_epoch", "started_at", "finished_at"):
        instant = record_instant_epoch(record=dict(stages), keys=(key,))
        if instant is not None:
            instants.append(instant)
    for stage in stages.values():
        instants.extend(_stage_instants(value=stage))
    return instants

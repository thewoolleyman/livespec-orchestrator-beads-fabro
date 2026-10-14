"""29f.6 metrics-heartbeat LivenessProbe — oyg watchdog deferred PRIMARY.

The DEFERRED-PRIMARY liveness signal the oyg `_dispatcher_watchdog`
docstring pins as an extension point. Spans emit on END, so a deadlocked
commit / wedged ACP turn produces ZERO spans for the whole hang (the
7us.6 failure mode) — a span-only signal is BLIND to a live-but-stuck
run. CC's metrics heartbeat exports on a SHORT interval and keeps
advancing while an agent turn is genuinely alive, so it is a finer,
earlier liveness signal than coarse event-stream timestamps (design
`loop-reflection-gate/telemetry-pipeline-architecture.md`
§4.3 / §4.4).

This module adds two seams, both feeding the EXISTING `decide_stall`
(its fail-safe policy is NOT rewritten here):

* `HeartbeatLivenessProbe` — a `LivenessProbe` that reads the
  journal-sibling heartbeat file the 29f.7 `HeartbeatSink` persists
  (`{run/session-key -> last-emit epoch}`) OUT OF PROCESS, looking the
  active run up by the candidate keys `heartbeat_lookup_keys` derives.
  It reports the FRESHEST matching beat as the sample's
  `last_event_epoch`, or None ("no signal") when no candidate key has
  ever beaten / the file is missing / the file is malformed. The read
  goes through `HeartbeatSink._read`, which is itself fail-open (a
  corrupt / unreadable file reads as empty), so a malformed heartbeat
  NEVER crashes the watchdog — it degrades to no signal.

* `LayeredLivenessProbe` — composes the heartbeat probe as the finer
  deferred-PRIMARY with the coarse wall-clock `fabro events` probe as
  the PERMANENT backstop, and reports whichever of the two carries the
  NEWER timestamp. This is the load-bearing degrade rule: an
  observability-pipeline outage degrades the watchdog to coarse
  event-stream detection — NEVER to NO detection. The wall-clock layer
  STAYS regardless, and since bd-ib-qsk4o5 it is never MASKED either.

Keying (§4.4 + the 29f.7 sink): the `HeartbeatSink` stores keys AFTER the
shared fail-closed `scrub` (so a credential-shaped id lands as the
redaction marker), keyed on the FIRST present of `fabro.run_id` /
`livespec.dispatch.id` / `work.item.id` / `session.id`. `fabro.run_id` is
NEVER among them in practice: `cc_otel_overlay_env` projects only
`work.item.id` and `livespec.dispatch.id` into the sandbox's
`OTEL_RESOURCE_ATTRIBUTES` (the fabro run id does not exist at projection
time), so `_preferred_key` always lands on `livespec.dispatch.id`. A
lookup by fabro run id therefore could never match a stored beat, which
is exactly how this probe silently read as "no signal" on every run until
the keys were realigned (plan `bd-ib-b5dg` research/008: 6/12 live
heartbeat keys were dispatch ids, 0/141 work-item and 0/147 run ids
matched). `heartbeat_lookup_keys` accordingly returns the SCRUBBED
work-item id (known at plan time) and dispatch id (minted by the
dispatcher before launch) — the SAME pair, in the same order, that
`_dispatcher_cost_sink.cost_lookup_keys` derives.

Pure of side effects beyond the injected `HeartbeatSink` read: the probe
samples are a function of the on-disk heartbeat plus the injected clock,
so the hermetic test tier drives every branch with synthetic heartbeat
files and never launches a real run.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessProbe,
    LivenessSample,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub

__all__: list[str] = [
    "HeartbeatLivenessProbe",
    "LayeredLivenessProbe",
    "heartbeat_lookup_keys",
]


def heartbeat_lookup_keys(*, work_item_id: str, dispatch_id: str | None) -> tuple[str, ...]:
    """The SCRUBBED candidate heartbeat keys for one in-flight dispatch.

    Mirrors `_dispatcher_cost_sink.cost_lookup_keys`: both key on
    `work.item.id` then `livespec.dispatch.id`, because those are the ONLY
    two ids `cc_otel_overlay_env` projects into the sandbox, so they are
    the only two the sink's `_preferred_key` can ever store a beat under.
    The work-item id is known at plan time and the dispatch id is minted
    before launch, so both are available to the watchdog. Empty /
    duplicate candidates are dropped (an empty id can never key a beat,
    and a duplicate would be a redundant lookup).

    Unlike the cost keys these ARE scrubbed, because the sink stores its
    keys after the shared fail-closed `scrub` — a lookup that skipped it
    would miss a beat the sink had redacted.
    """
    raw_candidates = (work_item_id, dispatch_id) if dispatch_id is not None else (work_item_id,)
    scrubbed: list[str] = []
    for candidate in raw_candidates:
        if candidate == "":
            continue
        key = scrub(value=candidate)
        if key not in scrubbed:
            scrubbed.append(key)
    return tuple(scrubbed)


@dataclass(frozen=True, kw_only=True)
class HeartbeatLivenessProbe:
    """A `LivenessProbe` reading the 29f.7 metrics-heartbeat file (29f.6).

    `sink` is the SAME `HeartbeatSink` the live receiver writes (pointed
    at the journal-sibling `<journal-stem>-otel-heartbeat.json`); `keys`
    are the SCRUBBED candidate work-item / dispatch keys (from
    `heartbeat_lookup_keys`). `sample` reads the FRESHEST last-emit
    timestamp across the candidate keys as the liveness signal, or None
    ("no signal") when no candidate has ever beaten.

    Fail-safe (load-bearing): the read goes through `HeartbeatSink`, whose
    `_read` is fail-open — a missing / corrupt / non-mapping file reads as
    empty rather than raising — so a malformed heartbeat NEVER crashes the
    watchdog. A None reading is the explicit fail-safe marker that
    `decide_stall` skips and that the `LayeredLivenessProbe` degrades to
    the wall-clock backstop on.
    """

    sink: HeartbeatSink
    keys: tuple[str, ...]

    def sample(self, *, observed_at: float) -> LivenessSample:
        """Read the freshest heartbeat across the candidate keys at `observed_at`."""
        beats = [beat for key in self.keys if (beat := self.sink.last_beat(key=key)) is not None]
        epoch = max(beats) if beats else None
        return LivenessSample(last_event_epoch=epoch, observed_at=observed_at)


@dataclass(frozen=True, kw_only=True)
class LayeredLivenessProbe:
    """Heartbeat and wall-clock backstop, reported as whichever is NEWER.

    Samples BOTH layers every poll and reports the newer of the two
    readings. `primary` is the deferred-PRIMARY heartbeat — the finer
    signal, because it advances on a short metrics-export interval — and
    `fallback` is the coarse `fabro events` wall-clock backstop; the names
    record which layer is finer and which is permanent, not an order of
    precedence. Either reading feeds the SAME `decide_stall` unchanged;
    this composition only chooses which layer supplies the sample, never
    the stall policy itself.

    REPORTING THE NEWER, rather than preferring the primary, is the repair
    of a measured false-kill (bd-ib-qsk4o5). This method used to return
    the primary sample whenever it carried ANY timestamp, so the fallback
    was never even read for the rest of the run. The two layers go quiet
    for DIFFERENT reasons and neither stands in for the other: the
    heartbeat is Claude Code's own metrics export, so it beats only while
    an AGENT turn is running and stops the instant the graph enters a
    COMMAND node — `janitor`, `publish_draft` — staying frozen for that
    node's whole duration however healthy the run is, while the event
    stream is the only layer that records that node starting. Measured on
    hp run 01M4QKN0R3N3: the last beat for dispatch
    f655b8d1f9b8423ab0e4009ee37d29dc was 09:30:53Z, when the second
    implement turn ended; the janitor went green at 09:52:05Z and the run
    was inside `publish_draft` when the watchdog cancelled it at
    09:57:54Z, with the event stream that recorded both nodes never read.
    Three of the six stall cancels on hp since 2026-10-08 were that shape.
    The same masking kills AGENT nodes whose adapter feeds the sink no
    beats: on hp run 01M4W9GCPB3B (2026-10-14) dispatch 87e54262's last
    beat was 04:11:33Z, when the Claude-adapter `dod_gate` ended; the
    codex-acp `implement` that followed beat nothing, and the run was
    cancelled at that beat plus the 7200 s window while `fabro events`
    carried tool activity up to 06:12:12Z.

    The degrade rule survives unchanged because it is a rule about
    ABSENCE, not about precedence: a layer that yields no signal
    contributes no timestamp, so the other answers alone, and only when
    BOTH are blind is the sample "no signal" — which `decide_stall` treats
    as keep-waiting. A frozen heartbeat beside a frozen event stream still
    confirms a stall, because neither reading advances.

    The open-command-node observation comes from the FALLBACK alone, and
    not out of any precedence between the layers: the event stream is the
    only layer carrying node lifecycle events at all, so the heartbeat has
    nothing to contribute to that question. Taking it from whichever layer
    reported the newer timestamp would instead drop it on every poll the
    heartbeat won — which is most polls inside an agent turn, while the
    bound exists precisely for the stretch after one ends.
    """

    primary: LivenessProbe
    fallback: LivenessProbe

    def sample(self, *, observed_at: float) -> LivenessSample:
        """Report the NEWER of the heartbeat and the wall-clock backstop."""
        primary_sample = self.primary.sample(observed_at=observed_at)
        fallback_sample = self.fallback.sample(observed_at=observed_at)
        epochs = [
            epoch
            for epoch in (primary_sample.last_event_epoch, fallback_sample.last_event_epoch)
            if epoch is not None
        ]
        return LivenessSample(
            last_event_epoch=max(epochs) if epochs else None,
            observed_at=observed_at,
            open_command_node=fallback_sample.open_command_node,
        )

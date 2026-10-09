"""Coarse wall-clock progress watchdog for the in-flight Fabro run.

Root cause this layer defends against (the 7us.6 incident): a Fabro run
wedged in `status=running` for 152 MINUTES emitting ZERO events after
`agent.session.activated` — a silent ACP/commit deadlock. The phase
graph's own `stall_timeout` (7200s, workflow.fabro `graph[...]`) did NOT
cancel it, and bn4's node-level retry/abandon never fired because the
run never reported a terminal status: it just sat alive emitting nothing,
burning a slot + spend for 2.5h until a human `fabro rm`-ed it. The
Dispatcher therefore needs its OWN host-side progress watchdog that does
not depend on any Fabro-internal machinery.

This module is the COARSE WALL-CLOCK BACKSTOP. Its liveness signal is the
last-event timestamp from the Fabro event stream (`fabro events <id>
--json`) and NOTHING ELSE: in the 7us.6 hang the event stream flatlined,
so a last-event-timestamp that stops advancing for a sustained window IS
a valid coarse liveness signal for this deadlock class. When no new event
arrives for the full stall window, the run is `fabro rm -f`-ed and the
dispatch reports a distinct `stalled-no-progress` outcome (fail-CLOSED —
never silently treated as success). There is deliberately NO `fabro
inspect` fallback; the REMOVED-FALLBACK note on `parse_last_event_epoch`
records why, and what was measured.

DEFERRED PRIMARY (extension point — DO NOT remove this backstop when it
lands): the eventual primary liveness signal is the 29f OpenTelemetry
metrics-heartbeat pipeline. Spans emit on END, so a deadlocked commit
produces NO span; a metrics heartbeat (exported on a short interval)
keeps advancing while an agent turn is genuinely alive and is a finer
signal than coarse event-stream timestamps. That pipeline does NOT exist
yet, so the metrics-heartbeat primary is NOT built here. When it lands it
plugs in as a finer `LivenessProbe` (see the Protocol below) feeding the
SAME `decide_stall` logic; this wall-clock layer STAYS as the permanent
defense-in-depth backstop, exactly so that an observability-pipeline
outage degrades the watchdog to coarse detection — never to NO detection.

Fail-safety (load-bearing): a probe FAILURE — `fabro events` transiently
errors or is unreachable — is "no signal", NOT a stall. `decide_stall`
only confirms a stall on the full window of genuinely-absent events (a
last-event timestamp that is present and unchanging across the whole
window). A run with no signal at all keeps waiting; a flaky probe can
never kill a healthy run. The coarse backstop
COEXISTS with bn4's 15h `_FABRO_TIMEOUT_SECONDS` subprocess ceiling
(_dispatcher_engine) — both stay, defense in depth.

Everything here is a pure function of its inputs (the clock is injected,
the event-stream JSON is parsed, the decision is computed) so the
hermetic test tier drives every branch without launching a real Fabro
run. The side-effecting orchestration (`fabro events` polling in the
foreground while `fabro run` executes in a background thread) lives in
`_dispatcher_engine`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Final, Protocol, cast

from livespec_orchestrator_beads_fabro.effects import (
    FloatParseFailure,
    IsoDatetimeParseFailure,
    JsonParseFailure,
    parse_float,
    parse_iso_datetime,
    parse_json,
)

__all__: list[str] = [
    "DEFAULT_STALL_SECONDS",
    "STALL_SECONDS_ENV_VAR",
    "LivenessProbe",
    "LivenessSample",
    "StallVerdict",
    "decide_stall",
    "parse_last_event_epoch",
    "resolve_stall_seconds",
]

# Coarse stall window (seconds of genuinely-absent events that confirm a
# stall). Calibration — this window must sit:
#   * WELL UNDER the phase graph's own `stall_timeout` = 7200s (2h,
#     workflow.fabro `graph[...]`): the host backstop must fire FIRST for
#     the 7us.6 hang class, which the Fabro-internal watchdog demonstrably
#     missed (152min of silence, never cancelled);
#   * WELL UNDER the implement node's per-turn ceiling = 14400s (4h,
#     workflow.fabro `implement[...]` timeout) and the engine's 15h
#     `_FABRO_TIMEOUT_SECONDS` subprocess ceiling;
#   * GENEROUSLY OVER the longest LEGITIMATE inter-event gap. The longest
#     legitimate quiet stretch is one `just check` leg inside the janitor
#     node — pytest + coverage + lint runs as a single Bash `tool_result`
#     that emits no fabro event until it returns; that is minutes, not
#     tens of minutes, even on the full aggregate.
# 1500s (25min) gives a single long `just check` leg comfortable margin
# (roughly 5x the observed worst-case aggregate) while still cancelling a
# true deadlock ~5x sooner than the 7200s Fabro watchdog would have (and
# it fired for the 7us.6 hang where Fabro's did not). Tune per dispatch
# via LIVESPEC_DISPATCH_STALL_SECONDS without a code change.
DEFAULT_STALL_SECONDS = 1500.0

# Env-var NAME (not a secret). An operator raises it for a known-slow
# repo/leg or lowers it to fail faster; an unset/blank/invalid value
# falls back to DEFAULT_STALL_SECONDS (a misconfigured window must never
# disable the backstop).
STALL_SECONDS_ENV_VAR = "LIVESPEC_DISPATCH_STALL_SECONDS"

# ISO-8601 timestamps Fabro emits in `events`/`inspect` JSON, e.g.
# "2026-06-13T08:16:24Z" or "...+00:00" or with fractional seconds. We
# normalize a trailing "Z" to "+00:00" so datetime.fromisoformat accepts
# it on the pinned Python (3.10, where fromisoformat does not parse "Z").
_TRAILING_Z_RE = re.compile(r"Z$")

# Event timestamp fields GROUPED BY UNIT, because a numeric timestamp means
# nothing without one. The second-valued names are what the pinned 0.254 build
# emitted; `recorded_at` is the Petri-era envelope's own field and counts
# MILLISECONDS (measured 2026-10-08 on 0.378.0-nightly.0, research note 006 of
# `plan/fabro-currency`). Keep a new field in the group matching its unit —
# moving `recorded_at` into the second-valued tuple blinds the stall watchdog.
_SECOND_EPOCH_FIELDS: tuple[str, ...] = ("timestamp", "ts", "at")
_MILLISECOND_EPOCH_FIELDS: tuple[str, ...] = ("recorded_at",)
_MILLISECONDS_PER_SECOND = 1000.0


@dataclass(frozen=True, kw_only=True)
class LivenessSample:
    """One observation of run liveness taken by the foreground watchdog.

    `last_event_epoch` is the most-recent event timestamp converted to
    epoch seconds, or None when the probe yielded NO usable signal (the
    `fabro events` call errored, returned an unparseable shape, or
    reported no events yet). `observed_at` is the wall-clock
    epoch the foreground watchdog took the sample (from the injected
    clock). A None `last_event_epoch` is the explicit fail-safe "no
    signal" marker `decide_stall` must NOT treat as a stall.
    """

    last_event_epoch: float | None
    observed_at: float


class LivenessProbe(Protocol):
    """The single liveness-signal seam the watchdog samples.

    Production reads the Fabro event stream (`fabro events <id> --json`)
    via the engine's `CommandRunner`. The
    DEFERRED 29f metrics-heartbeat primary will implement this SAME
    Protocol with a finer signal and feed the SAME `decide_stall`; this
    wall-clock implementation then stays as the coarse backstop. The
    hermetic test tier injects a scripted probe so no test launches a
    real run.
    """

    def sample(self, *, observed_at: float) -> LivenessSample:
        """Take one liveness observation at wall-clock epoch `observed_at`."""
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class StallVerdictValue:
    """Enum-like watchdog verdict value without subclassing."""

    value: str


class StallVerdict:
    """The watchdog's per-sample-window decision.

    `CONTINUE` — progress is being made (the last-event timestamp
    advanced within the window) OR there is no signal yet at all (no
    sample ever carried a timestamp): keep waiting.
    `STALLED` — a last-event timestamp was observed and has NOT advanced
    for the FULL stall window: a confirmed deadlock, cancel the run.
    """

    CONTINUE: Final = StallVerdictValue(value="continue")
    STALLED: Final = StallVerdictValue(value="stalled-no-progress")


def resolve_stall_seconds(*, environ: dict[str, str] | None = None) -> float:
    """Resolve the stall window from the env, defaulting to DEFAULT_STALL_SECONDS.

    Reads LIVESPEC_DISPATCH_STALL_SECONDS; an unset, blank, non-numeric,
    or non-positive value falls back to the default (a misconfigured
    window must never DISABLE the backstop or set a zero/negative window
    that would fire instantly). The resolved value is the only tunable;
    the decision logic is fixed.
    """
    env = dict(os.environ) if environ is None else environ
    raw = env.get(STALL_SECONDS_ENV_VAR, "")
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return DEFAULT_STALL_SECONDS
    value = parsed
    if value <= 0:
        return DEFAULT_STALL_SECONDS
    return value


def parse_last_event_epoch(*, events_json: str) -> float | None:
    """Extract the most-recent liveness timestamp as epoch seconds; None on no signal.

    Sole source: `fabro events <id> --json` — the maximum timestamp
    across all events (events may arrive out of order; the watchdog cares
    about the MOST RECENT activity, so it takes the max, never the last).
    Returns None when that source yields no usable timestamp — the
    explicit fail-safe "no signal" result the caller must NOT treat as a
    stall (a transient probe error lands here and keeps the run alive).

    Pure function of the events JSON blob; the side-effecting `fabro
    events` call happens in the engine through its CommandRunner.
    """
    # REMOVED FALLBACK (bd-ib-tec5sz) — REMOVED, not repointed, and this
    # note records which, and why, so it is not "revived" by a future
    # reader who reads the absence as an oversight.
    #
    # This function used to fall back to `updated_at` from `fabro inspect
    # <id> --json` when the event stream yielded nothing. The PINNED
    # fabro build (0.254.0, 8de6611) NEVER EMITS `updated_at`: measured
    # 2026-08-20 over six real payloads and re-confirmed 2026-08-22 on a
    # LIVE running run on the `hp` factory, an inspect record carries
    # exactly `checkpoint`, `conclusion`, `parent_id`, `run_id`,
    # `run_spec`, `sandbox`, `start_record`, `status` — and nothing else,
    # at any nesting level. The fallback was therefore dead code in
    # production. `fabro-enemy-unit-tests/test_tier0_watchdog_gap.py`
    # pins that absence against the live dependency.
    #
    # It is NOT repointed at `checkpoint.timestamp`, the only other
    # candidate on a RUNNING run (`conclusion.timestamp` exists only once
    # a run has concluded, so it can never report on a live one).
    # `checkpoint.timestamp` is written on NODE TRANSITION, so its
    # staleness is time-in-current-node, not time-since-last-activity.
    # Measured 2026-08-22: two healthy running runs sat 17 and 7 minutes
    # stale inside `start`, and run 01M0M9DEHMC4 spent 42m12s of its
    # 45m28s wall time inside inference-bearing nodes. Any window under
    # ~45 minutes would kill healthy runs — including that one, which
    # succeeded and merged its PR — while DEFAULT_STALL_SECONDS is 1500s
    # (25 min), and a window over 45 minutes is coarser than the graph's
    # own machinery this backstop exists to beat.
    #
    # Decisive on its own: the fallback fires exactly when the `fabro
    # events` probe yields nothing, i.e. on a probe OUTAGE. Feeding a
    # node-resolution clock in at that moment would convert this module's
    # load-bearing fail-safe rule ("a probe failure is no signal, NOT a
    # stall") into a false-KILL path. A fallback that reports healthy
    # runs as hung is worse than no fallback. `fabro events` stays the
    # sole coarse source; the finer signal is the deferred metrics
    # heartbeat (`_dispatcher_heartbeat_probe`), not an inspect field.
    return _max_event_epoch(events_json=events_json)


def decide_stall(
    *,
    samples: tuple[LivenessSample, ...],
    stall_seconds: float,
) -> StallVerdictValue:
    """Decide CONTINUE vs STALLED from the window of liveness samples. Fail-safe.

    The load-bearing fail-safety rule: a stall is confirmed ONLY when a
    last-event timestamp was actually OBSERVED and has stayed UNCHANGED
    across a span of wall-clock time >= `stall_seconds`. Concretely:

    * No sample ever carried a timestamp (every probe was "no signal") ->
      CONTINUE. A flaky / unreachable probe can never kill a healthy run.
    * The newest observed last-event timestamp is STRICTLY GREATER than
      the oldest observed one -> progress was made -> CONTINUE.
    * The newest observed last-event timestamp equals the oldest observed
      one AND the wall-clock span between those two OBSERVATIONS is
      >= `stall_seconds` -> the event stream has flatlined for the full
      window -> STALLED.
    * Otherwise (the timestamp is unchanged but the observed span is still
      under the window) -> CONTINUE (not yet confirmed; keep waiting).

    Only samples that carry a timestamp (`last_event_epoch is not None`)
    participate in the span/advance comparison; no-signal samples are
    skipped entirely, so a burst of probe failures in the middle of a
    healthy run cannot manufacture a false stall.
    """
    timestamped = tuple(sample for sample in samples if sample.last_event_epoch is not None)
    if len(timestamped) < 2:  # noqa: PLR2004 - need two real readings to compare
        return StallVerdict.CONTINUE
    first = timestamped[0]
    last = timestamped[-1]
    # mypy/pyright: filtered to non-None above.
    first_event = cast("float", first.last_event_epoch)
    last_event = cast("float", last.last_event_epoch)
    if last_event > first_event:
        return StallVerdict.CONTINUE
    observed_span = last.observed_at - first.observed_at
    if observed_span >= stall_seconds:
        return StallVerdict.STALLED
    return StallVerdict.CONTINUE


def _max_event_epoch(*, events_json: str) -> float | None:
    """Max event timestamp (epoch seconds) across `fabro events --json`; None on no signal."""
    parsed_raw = parse_json(text=events_json)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    events = _events_list(parsed_raw=parsed_raw)
    if events is None:
        return None
    epochs = [epoch for event in events if (epoch := _event_epoch(event_raw=event)) is not None]
    if not epochs:
        return None
    return max(epochs)


def _events_list(*, parsed_raw: object) -> list[object] | None:
    """Normalize the events payload to a list (top-level array or {"events": [...]})."""
    if isinstance(parsed_raw, list):
        return cast("list[object]", parsed_raw)
    if isinstance(parsed_raw, dict):
        events_raw: object = cast("dict[str, Any]", parsed_raw).get("events")
        if isinstance(events_raw, list):
            return cast("list[object]", events_raw)
    return None


def _event_epoch(*, event_raw: object) -> float | None:
    """Read one event's timestamp as epoch seconds, honouring each field's UNIT.

    The fields are grouped by unit rather than listed together, because a
    numeric timestamp means nothing without one. The pinned 0.254 build emitted
    `timestamp` / `ts` / `at` in SECONDS; the Petri-era build emits
    `recorded_at` in MILLISECONDS (measured 2026-10-08 on 0.378.0-nightly.0,
    research note 006 of `plan/fabro-currency`).

    Appending `recorded_at` to the second-valued group instead would read a
    millisecond value as epoch seconds and place every event in the year
    57000, which holds the observed span near zero and stops the stall
    watchdog ever firing — the fail-OPEN direction on a safety gauge.
    """
    if not isinstance(event_raw, dict):
        return None
    event = cast("dict[str, Any]", event_raw)
    for key in _SECOND_EPOCH_FIELDS:
        epoch = _epoch_value(value=event.get(key), per_second=1.0)
        if epoch is not None:
            return epoch
    for key in _MILLISECOND_EPOCH_FIELDS:
        epoch = _epoch_value(value=event.get(key), per_second=_MILLISECONDS_PER_SECOND)
        if epoch is not None:
            return epoch
    return None


def _epoch_value(*, value: object, per_second: float) -> float | None:
    """One field's value as epoch seconds; `per_second` carries the field's unit.

    An ISO STRING is never rescaled whatever group it was found under: it
    carries its own unit, so the divisor applies to the numeric form alone.
    """
    if isinstance(value, str):
        return _iso_to_epoch(value=value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value) / per_second
    return None


def _iso_to_epoch(*, value: str) -> float | None:
    """Parse an ISO-8601 timestamp to epoch seconds; None when unparseable.

    Normalizes a trailing `Z` to `+00:00` (the pinned Python 3.10
    `datetime.fromisoformat` does not accept `Z`) and treats a naive
    timestamp as UTC.
    """
    normalized = _TRAILING_Z_RE.sub("+00:00", value)
    parsed = parse_iso_datetime(text=normalized)
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()

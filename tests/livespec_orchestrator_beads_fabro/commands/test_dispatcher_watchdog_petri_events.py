"""The stall watchdog's liveness signal, read off a Petri-era event stream.

Plan `fabro-currency` P4 (`bd-ib-227cbw`). The coarse wall-clock backstop's ONLY
liveness signal is the newest event timestamp from `fabro events <id> --json`,
and on the Petri-era engine neither the field nor the container is what 0.254
emitted (research note 006, measured on v0.378.0-nightly.0 `64b9d88`):

- each record is an ENVELOPE keyed `{run_id, stream_seq, kind, id, recorded_at,
  item: {seq, recorded_at, record: {kind, body}}}`, where `recorded_at` is
  INTEGER MILLISECONDS — not the `timestamp` / `ts` / `at` the pinned build
  wrote, and not seconds;
- the note calls the output "a stream of envelopes", and the envelope carries a
  `stream_seq`, so the records can arrive as a newline-delimited stream rather
  than as one JSON array. The enemy harness has carried a line-parsing fallback
  for exactly that reason since before this item, so BOTH containers are
  asserted here rather than one guessed.

A watchdog that reads no timestamp reports "no signal", which `decide_stall`
must never treat as a stall — so the failure mode this closes is silent and
one-directional: every candidate run would look permanently unmeasurable and
the 7us.6 deadlock class would go undetected, which is the outage the backstop
exists for.

The two fixture envelopes are trimmed: research note 006 records that the first
record inlines the whole resolved run spec, which is irrelevant to a timestamp
read and is not reproduced.
"""

from __future__ import annotations

import json
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    parse_last_event_epoch,
)

_RUN_ID = "01M4DCQPCX6Z"
# 2026-10-08T12:34:29.813Z and 2026-10-08T12:34:55.207Z, as the engine writes
# them: integer milliseconds since the epoch.
_FIRST_RECORDED_AT_MS = 1791462869813
_LAST_RECORDED_AT_MS = 1791462895207
_LAST_RECORDED_AT_EPOCH_SECONDS = 1791462895.207


def _envelope(
    *, stream_seq: int, recorded_at_ms: int, kind: str, body: dict[str, Any]
) -> dict[str, Any]:
    return {
        "run_id": _RUN_ID,
        "stream_seq": stream_seq,
        "kind": kind,
        "id": f"{_RUN_ID}-{stream_seq}",
        "recorded_at": recorded_at_ms,
        "item": {
            "seq": stream_seq,
            "recorded_at": recorded_at_ms,
            "record": {"kind": kind, "body": body},
        },
    }


_PETRI_ENVELOPES: list[dict[str, Any]] = [
    _envelope(
        stream_seq=1,
        recorded_at_ms=_FIRST_RECORDED_AT_MS,
        kind="step.started",
        body={"event": "step.started", "firing": "implement", "attempt": 1},
    ),
    _envelope(
        stream_seq=2,
        recorded_at_ms=_LAST_RECORDED_AT_MS,
        kind="step.finished",
        body={"event": "step.finished", "outcome": "succeeded"},
    ),
]


def test_petri_recorded_at_milliseconds_are_read_as_the_newest_event_epoch() -> None:
    """The array container, and the millisecond unit converted to seconds."""
    epoch = parse_last_event_epoch(events_json=json.dumps(_PETRI_ENVELOPES))

    assert epoch == _LAST_RECORDED_AT_EPOCH_SECONDS


def test_petri_envelopes_are_read_from_a_newline_delimited_stream_too() -> None:
    """A stream of one envelope per line is the same reading as the array."""
    stream = "\n".join(json.dumps(envelope) for envelope in _PETRI_ENVELOPES) + "\n"

    assert parse_last_event_epoch(events_json=stream) == _LAST_RECORDED_AT_EPOCH_SECONDS


def test_the_legacy_timestamp_fields_are_still_read() -> None:
    """0.254 emitted ISO `timestamp`; the overlap needs both engines readable."""
    legacy = json.dumps(
        {
            "events": [
                {"timestamp": "2026-10-08T12:34:29Z", "event": "agent.session.activated"},
                {"timestamp": "2026-10-08T12:34:55Z", "event": "run.completed"},
            ]
        }
    )

    assert parse_last_event_epoch(events_json=legacy) == 1791462895.0


def test_an_unreadable_stream_is_still_no_signal_rather_than_a_stall() -> None:
    """Fail-safe: a probe that yields nothing readable can never kill a run."""
    assert parse_last_event_epoch(events_json="") is None
    assert parse_last_event_epoch(events_json="connection refused") is None
    assert parse_last_event_epoch(events_json='"a bare string"') is None
    assert parse_last_event_epoch(events_json=json.dumps([{"stream_seq": 1}])) is None


def test_a_flatlined_petri_stream_confirms_a_stall_through_the_same_decision() -> None:
    """End to end: the recorded_at reading is what the stall window compares."""
    epoch = parse_last_event_epoch(events_json=json.dumps(_PETRI_ENVELOPES))
    samples = (
        LivenessSample(last_event_epoch=epoch, observed_at=1000.0),
        LivenessSample(last_event_epoch=epoch, observed_at=2600.0),
    )

    assert decide_stall(samples=samples, stall_seconds=1500.0) == StallVerdict.STALLED

"""Event liveness reads the Petri envelope's `recorded_at`, in MILLISECONDS.

The Petri-era engine (0.378.0-nightly.0, measured 2026-10-08 — research note
006 of `plan/fabro-currency`) streams `fabro events --json` as envelopes
`{run_id, stream_seq, kind, id, recorded_at, item: {...}}` whose `recorded_at`
is an INTEGER COUNT OF MILLISECONDS. The pinned 0.254 build emitted
`timestamp` / `ts` / `at`, which is all the watchdog reads today, so on the
candidate every event yields no timestamp and `parse_last_event_epoch` returns
None — the run reads as having emitted no liveness signal at all.

THE UNIT IS THE WHOLE POINT, and it is why this cannot be fixed by appending
one name to the key tuple. The existing integer path treats an integer as epoch
SECONDS. A millisecond value read as seconds lands in the year 57000, so the
observed span between two samples stays near zero forever and the watchdog
NEVER fires. That is the fail-OPEN direction on a safety gauge: a wedged run
would hold its scheduler slot until the node's own ceiling killed it, and
nothing in the watchdog's output would say the gauge had been blinded.

So the millisecond assertion below is not a unit-conversion nicety. It is the
difference between a watchdog that can fire and one that cannot.
"""

from __future__ import annotations

import json
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    parse_last_event_epoch,
)

# 2025-10-09T08:53:20.123Z and one minute later, as the engine writes them.
_FIRST_MS = 1760000000123
_LAST_MS = 1760000060456


def _petri_envelope(*, seq: int, kind: str, recorded_at_ms: int) -> dict[str, Any]:
    return {
        "run_id": "01M4DCQPCX6Z",
        "stream_seq": seq,
        "kind": kind,
        "id": f"e{seq}",
        "recorded_at": recorded_at_ms,
        "item": {
            "seq": seq,
            "recorded_at": recorded_at_ms,
            "record": {"kind": kind, "body": {"event": kind}},
        },
    }


def test_recorded_at_milliseconds_become_epoch_seconds() -> None:
    events_json = json.dumps(
        [
            _petri_envelope(seq=1, kind="run.created", recorded_at_ms=_FIRST_MS),
            _petri_envelope(seq=2, kind="step.started", recorded_at_ms=_LAST_MS),
        ]
    )

    epoch = parse_last_event_epoch(events_json=events_json)

    assert epoch == _LAST_MS / 1000.0


def test_a_millisecond_value_is_never_reported_as_epoch_seconds() -> None:
    """The fail-open guard: the gauge must not place the event far in the future.

    Asserted as a magnitude rather than against the exact expected value so
    this still fails if a later edit reintroduces the raw-integer path by some
    other route. 1e11 seconds is the year 5138; any real event is far below it.
    """
    events_json = json.dumps(
        [_petri_envelope(seq=1, kind="step.finished", recorded_at_ms=_LAST_MS)]
    )

    epoch = parse_last_event_epoch(events_json=events_json)

    assert epoch is not None
    assert epoch < 1e11


def test_the_legacy_timestamp_fields_are_read_exactly_as_before() -> None:
    iso = json.dumps([{"timestamp": "2026-08-20T03:21:37Z"}])
    seconds = json.dumps([{"ts": 1755660097}])

    iso_epoch = parse_last_event_epoch(events_json=iso)
    seconds_epoch = parse_last_event_epoch(events_json=seconds)

    assert iso_epoch is not None
    # `ts` / `at` integers stay SECONDS — only `recorded_at` is a millisecond
    # field, so the legacy path must not be rescaled along with it.
    assert seconds_epoch == 1755660097.0

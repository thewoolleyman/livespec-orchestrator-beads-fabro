"""Fabro response records owned by the dispatcher Fabro port."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "FabroRunSummary",
    "FabroTokenUsage",
    "fabro_inspect_record",
    "fabro_run_id_from_output",
    "fabro_run_summaries_from_payload",
    "fabro_run_summaries_from_stdout",
    "fabro_status_kind_from_payload",
    "fabro_token_usage_from_payload",
]

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")
_WORK_ITEM_RE = re.compile(r"^Work-item:\s*(\S+)", re.MULTILINE)

# The event whose body carries token counts on the Petri-era build. Named for
# the USAGE it reports rather than for the word "token", which reads as a
# credential to the hardcoded-secret lint and is not one.
_USAGE_EVENT_KIND = "token.emitted"
# Body field spellings accepted for each direction. The body was never
# measured (see `FabroTokenUsage`), so this is a tolerance rather than a
# schema: the FIRST recognized spelling in a body wins, and a body matching
# none of them contributes nothing instead of contributing zero.
_INPUT_TOKEN_KEYS: tuple[str, ...] = ("input_tokens", "prompt_tokens", "tokens_in", "input")
_OUTPUT_TOKEN_KEYS: tuple[str, ...] = (
    "output_tokens",
    "completion_tokens",
    "tokens_out",
    "output",
)


@dataclass(frozen=True, kw_only=True)
class FabroRunSummary:
    """Run row from `fabro ps -a --json` that livespec code reads.

    `wall_time_ms` is the Petri-era build's own duration field (measured
    2026-10-08 on 0.378.0-nightly.0, research note 006 of
    `plan/fabro-currency`); the pinned 0.254 build carried no such key, so it
    is `None` there. It rides beside `total_usd_micros` deliberately: a cost
    reaching the audit path with no measure of what it bought can be read only
    as a number, not as cheap or expensive.

    An ABSENT duration is `None`, never `0`, for the reason an absence is never
    zero anywhere in this port: a zero-millisecond run is a measurement and a
    missing field is not.
    """

    run_id: str
    status_kind: str | None
    goal: str | None
    total_usd_micros: int | None
    wall_time_ms: int | None = None
    work_item_id: str | None = field(default=None, compare=False)


@dataclass(frozen=True, kw_only=True)
class FabroTokenUsage:
    """Token counts summed from a run's `token.emitted` events.

    The Petri-era build emits `token.emitted` into the event stream, which is
    the first token signal to exist at all: on 0.254 `fabro events` carried no
    cost or token field whatsoever — the measurement `_dispatcher_cost`'s own
    docstring records.

    THE BODY'S FIELD NAMES WERE NEVER MEASURED. Research notes 006 and 007 name
    the event and record nothing of its body, so the reader accepts the usual
    spellings rather than one this repository has never seen, and reports `None`
    when it recognizes none of them. That is also why there is no zero-valued
    construction path: a confident zero is indistinguishable from a body nobody
    could parse, and the two support opposite conclusions about whether the
    engine emits the signal at all.
    """

    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def fabro_run_id_from_output(*, output: str) -> str | None:
    plain = _ANSI_ESCAPE_RE.sub("", output)
    match = _RUN_ID_RE.search(plain)
    if match is None:
        return None
    return match.group(1)


def fabro_run_summaries_from_stdout(*, stdout: str) -> tuple[FabroRunSummary, ...]:
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return ()
    return fabro_run_summaries_from_payload(payload=parsed)


def fabro_run_summaries_from_payload(*, payload: object | None) -> tuple[FabroRunSummary, ...]:
    summaries: list[FabroRunSummary] = []
    for run in _runs(payload=payload):
        summary = _run_summary(run=run)
        if summary is not None:
            summaries.append(summary)
    return tuple(summaries)


def fabro_inspect_record(*, payload: object | None) -> dict[str, Any] | None:
    """Normalize an `inspect` payload to the single run record it describes.

    `fabro inspect <run> --json` returns a single-element LIST on the pinned
    build (0.254.0), not a bare mapping. Measured against six real payloads on
    2026-08-20. Mapping payloads are still accepted so a future shape change
    back to a bare object does not regress.
    """
    if isinstance(payload, dict):
        return cast("dict[str, Any]", payload)
    if isinstance(payload, list):
        for entry in cast("list[object]", payload):
            if isinstance(entry, dict):
                return cast("dict[str, Any]", entry)
    return None


def fabro_status_kind_from_payload(*, payload: object | None) -> str | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    status_raw: object = record.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def fabro_token_usage_from_payload(*, payload: object | None) -> FabroTokenUsage | None:
    """Token counts summed over a run's `token.emitted` events, or None if absent.

    `None` says this stream carried NO recognizable token signal, which is both
    the 0.254 case (the event does not exist there) and the case of a Petri body
    whose field names this reader does not know. Those two are deliberately one
    answer: each means "no token evidence was read", and neither licenses
    reporting a count.
    """
    totals = [
        counts
        for event in _events(payload=payload)
        if (counts := _token_counts(event=event)) is not None
    ]
    if not totals:
        return None
    return FabroTokenUsage(
        input_tokens=sum(entry[0] for entry in totals),
        output_tokens=sum(entry[1] for entry in totals),
    )


def _events(*, payload: object | None) -> list[object]:
    """The event list, whether the stream is a bare array or an `events` wrapper."""
    if isinstance(payload, list):
        return cast("list[object]", payload)
    if isinstance(payload, dict):
        events_raw: object = cast("dict[str, Any]", payload).get("events")
        if isinstance(events_raw, list):
            return cast("list[object]", events_raw)
    return []


def _token_counts(*, event: object) -> tuple[int, int] | None:
    """One `token.emitted` body's (input, output) counts, or None.

    Returns None for any event that is not a token event AND for a token event
    whose body names neither direction — the distinction between "not a token
    event" and "an unreadable token event" is not one the caller can act on
    differently, and collapsing it here keeps the sum free of invented zeroes.
    """
    if not isinstance(event, dict):
        return None
    body = _token_event_body(event=cast("dict[str, Any]", event))
    if body is None:
        return None
    input_tokens = _first_int(mapping=body, keys=_INPUT_TOKEN_KEYS)
    output_tokens = _first_int(mapping=body, keys=_OUTPUT_TOKEN_KEYS)
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0, output_tokens or 0)


def _token_event_body(*, event: dict[str, Any]) -> dict[str, Any] | None:
    """The token event's body, reached through the Petri envelope's `item.record`.

    The envelope nests the Petri body two levels down (`item.record.body`), and
    the `kind` is carried on BOTH the envelope and the record. The envelope's
    own `kind` is read first because it is the cheaper discriminator; the record
    is then the only place the body can be.
    """
    if event.get("kind") != _USAGE_EVENT_KIND:
        return None
    item: object = event.get("item")
    if not isinstance(item, dict):
        return None
    record: object = cast("dict[str, Any]", item).get("record")
    if not isinstance(record, dict):
        return None
    body: object = cast("dict[str, Any]", record).get("body")
    if not isinstance(body, dict):
        return None
    return cast("dict[str, Any]", body)


def _first_int(*, mapping: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """The first recognized spelling's integer value, or None if none is present."""
    for key in keys:
        value = _optional_int(value=mapping.get(key))
        if value is not None:
            return value
    return None


def _runs(*, payload: object | None) -> list[object]:
    if isinstance(payload, list):
        return cast("list[object]", payload)
    if isinstance(payload, dict):
        runs_raw: object = cast("dict[str, Any]", payload).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def _run_summary(*, run: object) -> FabroRunSummary | None:
    if not isinstance(run, dict):
        return None
    record = cast("dict[str, Any]", run)
    run_id_raw: object = record.get("run_id")
    if not isinstance(run_id_raw, str) or run_id_raw == "":
        return None
    goal = _optional_str(value=record.get("goal"))
    return FabroRunSummary(
        run_id=run_id_raw,
        status_kind=fabro_status_kind_from_payload(payload=record),
        goal=goal,
        work_item_id=_work_item_id(goal=goal),
        total_usd_micros=_optional_int(value=record.get("total_usd_micros")),
        wall_time_ms=_optional_int(value=record.get("wall_time_ms")),
    )


def _optional_str(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(*, value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _work_item_id(*, goal: str | None) -> str | None:
    if goal is None:
        return None
    match = _WORK_ITEM_RE.search(goal)
    return None if match is None else match.group(1)

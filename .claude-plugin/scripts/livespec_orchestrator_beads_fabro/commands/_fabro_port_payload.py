"""Fabro CLI payload parsing shared by the facade's JSON-returning verbs."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroCommand
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "fabro_events_payload",
    "fabro_json_payload",
]


def fabro_events_payload(*, command: FabroCommand) -> object | None:
    """The events output as a payload, reading the Petri stream form as well.

    `fabro events --json` prints one JSON array on the pinned build and "a
    stream of envelopes" on the Petri-era one (research note 006), and a stream
    is not one JSON document, so the ordinary whole-text parse yields nothing
    for it. The fallback hands the records back as a LIST — the shape every
    consumer of this payload already accepts — so from here on the two engines'
    streams project identically rather than through two readers.

    A NON-ZERO exit keeps its `None`, and so does output nothing could be read
    from. "Read failure is not absence" is what the ACP projection grades an
    unreadable fetch by, so a refusal's own message must never arrive as an
    empty event list, which reads as a run that emitted nothing.
    """
    payload = fabro_json_payload(command=command)
    if payload is not None or command.exit_code != 0:
        return payload
    records = fabro_event_records_from_stdout(stdout=command.stdout)
    return None if records is None else list(records)


def fabro_json_payload(*, command: FabroCommand) -> object | None:
    if command.exit_code != 0:
        return None
    parsed = parse_json(text=command.stdout)
    if isinstance(parsed, JsonParseFailure):
        return None
    return parsed

"""One relay record's WIRE FORM: the comment body it travels in, and its payload.

PURE. `_plan_relay_record` owns the VALUE; this owns the bytes the ledger holds
it as. The two are separate concerns and the dependency runs one way — a record
knows nothing about how it is rendered, while every renderer and reader here is
about one record.

THE RENDER AND THE PARSE STAY IN ONE MODULE deliberately. They are one format,
and a format whose halves sit in different files drifts: the renderer gains a
field, the parse keeps answering for the shape it knew, and every record written
afterwards reads back as the subset the older half understood. `plan_comment_body`
and `_parse_entry` are kept together one module over for the same reason.

WHY THE COMMENT CARRIES A CANONICAL PAYLOAD AS WELL AS READABLE LINES. This is
the requirement `_plan_epoch_projection` carries for the progress event, and the
relay clause of `SPECIFICATION/contracts.md` sharpens it: "Retrying the same
operation identity for an existing relay MUST return its recorded observation".
Prose cannot be parsed back into an observation, so a retry answered from the
readable lines would answer with an observation nobody took. `bd comments` offers
no edit and no delete, so what is written here is permanent.

WHY EVERY MALFORMED PAYLOAD PARSES TO `None` RATHER THAN TO A PARTIAL RECORD. A
retry is answered from a parsed payload, so a half-read one would answer with an
observation the READER assembled — satisfaction included, on the arm where a
`delivered` flag survived and the observation beside it did not.
"""

from __future__ import annotations

import json
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    RelayLegs,
    RelayRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import ResultObservation
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "OBSERVATION_STATUSES",
    "PLAN_RELAY_PREFIX",
    "parse_relay_payload",
    "payload_line",
    "relay_event_body",
    "render_relay_payload",
]

# The fixed first line. `read_timeline` filters on the handoff and scope
# prefixes only, so a relay event never enters the plan timeline a resume reads
# for self-sufficiency findings — a relay is an obligation record, not a handoff.
PLAN_RELAY_PREFIX = "plan-relay-event"

# The three statuses `ResultObservation` admits, restated here because a parse
# reading an arbitrary string into that field would reconstruct an observation
# whose status no reader produced.
OBSERVATION_STATUSES = ("satisfied", "unsatisfied", "unobservable")

_PAYLOAD_LABEL = "payload: "
_STRING_FIELDS = (
    "relay_id",
    "operation_id",
    "sender",
    "result_identity",
    "original_deadline",
    "recorded_at",
)
_LEG_FIELDS = ("receipt_ack", "peer_recorded", "target_evidence")
_OBSERVATION_FIELDS = (
    "status",
    "repo",
    "target",
    "source",
    "observed_at",
    "evidence",
    "detail",
)


def render_relay_payload(*, record: RelayRecord) -> str:
    """Render one record as the canonical one-line JSON the comment carries."""
    observation = record.observation
    return json.dumps(
        {
            "relay_id": record.relay_id,
            "operation_id": record.operation_id,
            "sender": record.sender,
            "required_result": record.required_result,
            "result_identity": record.result_identity,
            "original_deadline": record.original_deadline,
            "delivered": record.delivered,
            "recorded_at": record.recorded_at,
            "legs": {
                "receipt_ack": record.legs.receipt_ack,
                "peer_recorded": record.legs.peer_recorded,
                "target_evidence": record.legs.target_evidence,
            },
            "observation": {
                "status": observation.status,
                "repo": observation.repo,
                "target": observation.target,
                "source": observation.source,
                "observed_at": observation.observed_at,
                "evidence": observation.evidence,
                "detail": observation.detail,
            },
            "superseded_relay_id": record.superseded_relay_id,
            "superseded_disposition": record.superseded_disposition,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def parse_relay_payload(*, text: str) -> RelayRecord | None:
    """Read one canonical payload back, or `None` when it is not one."""
    parsed = parse_json(text=text)
    fields = None if isinstance(parsed, JsonParseFailure) else _object(value=parsed)
    if fields is None:
        return None
    legs = _legs(value=fields.get("legs"))
    observation = _observation(value=fields.get("observation"))
    strings = _strings(fields=fields)
    delivered = fields.get("delivered")
    if legs is None or observation is None or strings is None or not isinstance(delivered, bool):
        return None
    return RelayRecord(
        relay_id=strings[0],
        operation_id=strings[1],
        sender=strings[2],
        required_result=fields.get("required_result"),
        result_identity=strings[3],
        original_deadline=strings[4],
        delivered=delivered,
        legs=legs,
        observation=observation,
        recorded_at=strings[5],
        superseded_relay_id=_nullable(value=fields.get("superseded_relay_id")),
        superseded_disposition=_nullable(value=fields.get("superseded_disposition")),
    )


def relay_event_body(*, record: RelayRecord) -> str:
    """Render the event's readable lines, then its canonical payload."""
    observation = record.observation
    lines = [
        f"relay: {record.relay_id}",
        f"operation: {record.operation_id}",
        f"sender: {record.sender}",
        f"delivery: {record.disposition}",
        f"result: {record.result_identity}",
        f"original-deadline: {record.original_deadline}",
        f"observation: {observation.status} via {observation.source} at {observation.observed_at}",
        f"evidence: {observation.evidence}",
        f"receipt-ack: {record.legs.receipt_ack}",
        f"peer-recorded: {record.legs.peer_recorded}",
        f"target-evidence: {record.legs.target_evidence}",
        f"ownership-transferable: {record.ownership_transferable}",
    ]
    if record.superseded_relay_id is not None:
        lines.append(f"supersedes: {record.superseded_relay_id} ({record.superseded_disposition})")
    lines.append(f"detail: {observation.detail}")
    lines.append(f"{_PAYLOAD_LABEL}{render_relay_payload(record=record)}")
    return "\n".join(lines)


def payload_line(*, text: str) -> str | None:
    """The canonical payload one event body carries, or `None` for none."""
    for line in text.splitlines():
        if line.startswith(_PAYLOAD_LABEL):
            value = line.removeprefix(_PAYLOAD_LABEL).strip()
            if value != "":
                return value
    return None


def _object(*, value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _nullable(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def _strings(*, fields: dict[str, Any]) -> tuple[str, ...] | None:
    """The six required string fields, or `None` when any is absent or ill-typed."""
    values = [fields.get(key) for key in _STRING_FIELDS]
    if not all(isinstance(value, str) for value in values):
        return None
    return tuple(cast("list[str]", values))


def _legs(*, value: object) -> RelayLegs | None:
    fields = _object(value=value)
    if fields is None:
        return None
    read = [fields.get(key) for key in _LEG_FIELDS]
    if not all(isinstance(leg, str | None) for leg in read):
        return None
    return RelayLegs(
        receipt_ack=_nullable(value=read[0]),
        peer_recorded=_nullable(value=read[1]),
        target_evidence=_nullable(value=read[2]),
    )


def _observation(*, value: object) -> ResultObservation | None:
    fields = _object(value=value)
    if fields is None:
        return None
    read = [fields.get(key) for key in _OBSERVATION_FIELDS]
    if not all(isinstance(field, str) for field in read):
        return None
    text = cast("list[str]", read)
    if text[0] not in OBSERVATION_STATUSES:
        return None
    return ResultObservation(
        status=cast("Any", text[0]),
        repo=text[1],
        target=text[2],
        source=text[3],
        observed_at=text[4],
        evidence=text[5],
        detail=text[6],
    )

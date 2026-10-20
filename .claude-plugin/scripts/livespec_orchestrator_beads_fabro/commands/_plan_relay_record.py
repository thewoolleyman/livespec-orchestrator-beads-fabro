"""One relay, as the ledger records it: its three delivery legs and its payload.

PURE. `contracts.md` section "Relay delivery" fixes what a relay record carries:
"The plan primitive recording a relay MUST accept a stable relay id, typed
expected result and absolute UTC deadline, and MUST read the target before
recording `delivered`." This module is that record — the value, its canonical
payload, and the `plan-relay-event` comment body the epic carries it in.

THE THREE LEGS ARE NOT INTERCHANGEABLE, AND ONLY ONE OF THEM IS EVIDENCE. The
same clause says "A sender queue receipt, peer acknowledgment or peer_recorded
value MUST NOT establish delivery", and separately that the obligation schema
"MUST retain receipt_ack and peer_recorded and add the target-evidence delivery
leg; ownership transfer/closure requires all three". So `RelayLegs` holds all
three, while the CALLER may supply only two: `RelayAcknowledgements` carries
`receipt_ack` and `peer_recorded`, and `target_evidence` is filled in by the
primitive from an authoritative SATISFIED observation and from nothing else. A
caller-supplied target evidence would be the sender certifying its own delivery,
which is the exact substitution the clause exists to refuse — and it would be
invisible, because a record carrying all three legs reads as a discharged relay
whoever wrote the third.

WHY `delivered` IS A FIELD AND NOT A PROPERTY OF THE LEGS. A reader deriving
delivery from "the third leg is present" would be deriving it from a string the
record happens to hold, so a record whose evidence line was written by anything
other than a satisfied read would read as delivered. The field is written once,
by the one caller that performed the read, and `ownership_transferable` is the
conjunction a transfer or closure asks for.

WHY THE COMMENT CARRIES A CANONICAL PAYLOAD AS WELL AS READABLE LINES. This is
the same requirement `_plan_epoch_projection` carries for the progress event, and
the relay clause sharpens it: "Retrying the same operation identity for an
existing relay MUST return its recorded observation". Prose cannot be parsed back
into an observation, so a retry answered from the readable lines would answer
with an observation nobody took. `bd comments` offers no edit and no delete, so
what is written here is permanent.

WHY THE SUPERSESSION IS TWO FIELDS ON THE SUCCESSOR RATHER THAN A MUTATION OF THE
PREDECESSOR. "a conflicting target requires a new explicit supersession that
preserves the old obligation's disposition" — and the predecessor's own record
cannot be edited, so the only place the old disposition can be preserved is the
record that replaces it. Keeping the predecessor's relay id beside its
disposition is what lets a reader walk from the live obligation back to the one
it displaced without re-deriving a disposition from records written later.

WHY EVERY MALFORMED PAYLOAD PARSES TO `None` RATHER THAN TO A PARTIAL RECORD. A
retry is answered from a parsed payload, so a half-read one would answer with an
observation the READER assembled — satisfaction included, on the arm where a
`delivered` flag survived and the observation beside it did not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_result_observation import ResultObservation
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "DELIVERY_DELIVERED",
    "DELIVERY_UNDELIVERED",
    "OBSERVATION_STATUSES",
    "PLAN_RELAY_PREFIX",
    "RelayAcknowledgements",
    "RelayLegs",
    "RelayRecord",
    "latest_relay",
    "parse_relay_payload",
    "payload_line",
    "recorded_operation",
    "relay_event_body",
    "render_relay_payload",
]

# The fixed first line. `read_timeline` filters on the handoff and scope
# prefixes only, so a relay event never enters the plan timeline a resume reads
# for self-sufficiency findings — a relay is an obligation record, not a handoff.
PLAN_RELAY_PREFIX = "plan-relay-event"

DELIVERY_DELIVERED = "delivered"
DELIVERY_UNDELIVERED = "undelivered"

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


@dataclass(frozen=True, kw_only=True)
class RelayAcknowledgements:
    """The two legs a CALLER may supply: transport receipt and peer recording.

    Neither establishes anything about the target. They are recorded because the
    clause requires the schema to retain them, and they are kept apart from the
    third leg because a type that let a caller write target evidence would make
    the separation a convention rather than a property.
    """

    receipt_ack: str | None = None
    peer_recorded: str | None = None


@dataclass(frozen=True, kw_only=True)
class RelayLegs:
    """All three delivery legs of one recorded relay."""

    receipt_ack: str | None
    peer_recorded: str | None
    target_evidence: str | None

    @property
    def complete(self) -> bool:
        """Whether all three legs are present, which is what a transfer needs."""
        legs = (self.receipt_ack, self.peer_recorded, self.target_evidence)
        return all(leg is not None and leg.strip() != "" for leg in legs)


@dataclass(frozen=True, kw_only=True)
class RelayRecord:
    """One observation of one relay, as the `plan-relay-event` comment carries it.

    `original_deadline` is the FIRST deadline this relay id was ever recorded
    under. Every later observation of the same relay re-renders it unchanged,
    which is the guarantee the clause words as "its unchanged deadline".
    """

    relay_id: str
    operation_id: str
    sender: str
    required_result: object
    result_identity: str
    original_deadline: str
    delivered: bool
    legs: RelayLegs
    observation: ResultObservation
    recorded_at: str
    superseded_relay_id: str | None = None
    superseded_disposition: str | None = None

    @property
    def disposition(self) -> str:
        """The one word a reader of this relay's state needs."""
        return DELIVERY_DELIVERED if self.delivered else DELIVERY_UNDELIVERED

    @property
    def ownership_transferable(self) -> bool:
        """Whether ownership may transfer or the obligation close.

        Both halves are asked for, even though a satisfied read is what writes
        the third leg: a record restored from a payload carries whatever was
        written, so reading the conjunction keeps the rule stated where the
        transfer is decided rather than inferred from one field's provenance.
        """
        return self.delivered and self.legs.complete


def latest_relay(*, records: tuple[RelayRecord, ...], relay_id: str) -> RelayRecord | None:
    """The newest recorded observation of one relay id, or `None` for none."""
    matching = [record for record in records if record.relay_id == relay_id]
    return matching[-1] if matching else None


def recorded_operation(
    *, records: tuple[RelayRecord, ...], operation_id: str
) -> RelayRecord | None:
    """The record one operation identity already produced, or `None` for none.

    The FIRST match rather than the newest, because an operation identity names
    one act: a retry must be answered with what that act recorded, and a later
    record carrying the same identity would be a second act wearing its name.
    """
    for record in records:
        if record.operation_id == operation_id:
            return record
    return None


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

"""One relay, as an obligation: its three delivery legs and the observation of it.

PURE, and the VALUE half of the relay record. Its wire form — the canonical
payload and the `plan-relay-event` comment body — is `_plan_relay_payload`, and
the dependency runs one way: a record knows nothing about how it is rendered.

PURE. `contracts.md` section "Relay delivery" fixes what a relay record carries:
"The plan primitive recording a relay MUST accept a stable relay id, typed
expected result and absolute UTC deadline, and MUST read the target before
recording `delivered`."

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

WHY THE SUPERSESSION IS TWO FIELDS ON THE SUCCESSOR RATHER THAN A MUTATION OF THE
PREDECESSOR. "a conflicting target requires a new explicit supersession that
preserves the old obligation's disposition" — and the predecessor's own record
cannot be edited, so the only place the old disposition can be preserved is the
record that replaces it. Keeping the predecessor's relay id beside its
disposition is what lets a reader walk from the live obligation back to the one
it displaced without re-deriving a disposition from records written later.

WHY THE TWO SELECTIONS DIFFER IN WHICH MATCH THEY TAKE. A relay accumulates
observations, so its LIVE state is the newest record under its id; an operation
identity names ONE act, so a retry is owed what that act recorded and the first
match is the only one that can be it.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._plan_result_observation import ResultObservation

__all__: list[str] = [
    "DELIVERY_DELIVERED",
    "DELIVERY_UNDELIVERED",
    "RelayAcknowledgements",
    "RelayLegs",
    "RelayRecord",
    "latest_relay",
    "recorded_operation",
]

DELIVERY_DELIVERED = "delivered"
DELIVERY_UNDELIVERED = "undelivered"


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
    under, and `sender` is the party that owed it then. Every later observation
    of the same relay re-renders BOTH unchanged, which is the guarantee the
    clause words as "its unchanged deadline" and as "Timeout MUST retain sender
    ownership ... while the independent consumer performs bounded recovery".

    So `sender` names the owner and never the recorder: an independent
    consumer's recheck is attributed by its own `operation_id`, while `sender`
    keeps naming whoever an expiry falls to until `ownership_transferable`
    admits a transfer.
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

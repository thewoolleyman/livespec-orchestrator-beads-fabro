"""The relay record: its three legs, its selections, and its canonical payload.

The integration tier binds Scenario 149 end to end. This module covers what the
record itself owns and that tier cannot reach: the round trip through the
canonical payload, every malformed shape it must refuse, and the two selections
a retry and a recheck resolve a relay through.
"""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    DELIVERY_DELIVERED,
    DELIVERY_UNDELIVERED,
    RelayLegs,
    RelayRecord,
    latest_relay,
    parse_relay_payload,
    payload_line,
    recorded_operation,
    relay_event_body,
    render_relay_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    ResultObservation,
    satisfied,
    unsatisfied,
)

_RELAY = "relay-1"
_RESULT = "repo item_status bd-ib-target status done"
_DEADLINE = "2026-10-20T18:00:00Z"


def _observation(*, met: bool) -> ResultObservation:
    if met:
        return satisfied(
            repo="repo",
            target=_RESULT,
            source="ledger",
            now="2026-10-20T09:00:00Z",
            evidence="bd-ib-target at status done",
            detail="the item stands at the expected status",
        )
    return unsatisfied(
        repo="repo",
        target=_RESULT,
        source="ledger",
        now="2026-10-20T09:00:00Z",
        evidence="bd-ib-target at status active",
        detail="the item does not stand at the expected status",
    )


def _record(
    *,
    met: bool = False,
    relay_id: str = _RELAY,
    operation_id: str = "op-1",
    superseded: str | None = None,
) -> RelayRecord:
    observation = _observation(met=met)
    return RelayRecord(
        relay_id=relay_id,
        operation_id=operation_id,
        sender="plan-supervisor",
        required_result={"repo": "repo", "item_status": {"item_id": "bd-ib-target"}},
        result_identity=_RESULT,
        original_deadline=_DEADLINE,
        delivered=met,
        legs=RelayLegs(
            receipt_ack="2026-10-20T08:55:00Z",
            peer_recorded="2026-10-20T08:56:00Z",
            target_evidence=observation.evidence if met else None,
        ),
        observation=observation,
        recorded_at="2026-10-20T09:00:00Z",
        superseded_relay_id=superseded,
        superseded_disposition=None if superseded is None else DELIVERY_UNDELIVERED,
    )


def test_the_two_transport_legs_never_complete_the_set_on_their_own() -> None:
    """Receipt and peer recording are retained, and they discharge nothing.

    `complete` is what a transfer or a closure asks, so a set that read as
    complete without the evidence leg would hand ownership away on a transport
    acknowledgment — the substitution the clause exists to refuse.
    """
    acknowledged = _record(met=False)

    assert acknowledged.legs.receipt_ack is not None
    assert acknowledged.legs.peer_recorded is not None
    assert acknowledged.legs.complete is False
    assert acknowledged.ownership_transferable is False
    assert acknowledged.disposition == DELIVERY_UNDELIVERED


def test_an_evidence_leg_present_but_blank_does_not_complete_the_set() -> None:
    """A whitespace leg is an absent leg.

    An empty string is what a renderer writes when it had nothing to write, so
    reading one as a present leg would let a record assembled from an empty
    evidence field transfer ownership.
    """
    legs = RelayLegs(receipt_ack="a", peer_recorded="b", target_evidence="   ")

    assert legs.complete is False


def test_a_delivered_record_with_all_three_legs_may_transfer_ownership() -> None:
    """The positive control: the same reading, with the evidence a real read left."""
    delivered = _record(met=True)

    assert delivered.disposition == DELIVERY_DELIVERED
    assert delivered.legs.complete is True
    assert delivered.ownership_transferable is True


def test_a_record_survives_the_canonical_payload_round_trip() -> None:
    """A retry is answered from the parse, so the parse must return the record."""
    for record in (_record(met=False), _record(met=True), _record(superseded="relay-0")):
        assert parse_relay_payload(text=render_relay_payload(record=record)) == record


def test_the_event_body_names_a_superseded_relay_and_carries_the_payload() -> None:
    """The successor is the only place the displaced obligation can be preserved.

    `bd comments` offers no edit, so the predecessor's record cannot be amended;
    the clause's "preserves the old obligation's disposition" therefore has to be
    satisfied by the record that replaces it.
    """
    body = relay_event_body(record=_record(superseded="relay-0"))

    assert "supersedes: relay-0 (undelivered)" in body
    payload = payload_line(text=body)
    assert payload is not None
    assert parse_relay_payload(text=payload) is not None


def test_an_event_body_without_a_supersession_names_none() -> None:
    """The ordinary relay carries no supersession line at all."""
    assert "supersedes:" not in relay_event_body(record=_record())


@pytest.mark.parametrize(
    "text",
    [
        "relay: relay-1\nno payload here",
        "payload:   ",
    ],
)
def test_a_body_carrying_no_usable_payload_line_reads_as_none(text: str) -> None:
    """An absent and a blank payload are the same absence to every reader."""
    assert payload_line(text=text) is None


def _mutated(*, change: dict[str, object]) -> str:
    fields = json.loads(render_relay_payload(record=_record()))
    fields.update(change)
    return json.dumps(fields)


@pytest.mark.parametrize(
    "change",
    [
        {"relay_id": 1},
        {"delivered": "yes"},
        {"legs": "none"},
        {"legs": {"receipt_ack": 1, "peer_recorded": None, "target_evidence": None}},
        {"observation": "none"},
        {"observation": {"status": "satisfied"}},
    ],
)
def test_every_malformed_payload_reads_as_no_record_at_all(change: dict[str, object]) -> None:
    """Fail closed on every partial read.

    A half-read payload would answer a retry with an observation this reader
    assembled rather than the one that was recorded — and on the `delivered`
    field that is a discharge nobody observed.
    """
    assert parse_relay_payload(text=_mutated(change=change)) is None


def test_a_payload_whose_observation_status_is_not_one_of_the_three_is_refused() -> None:
    """`ResultObservation` admits three statuses; a fourth is not an observation."""
    fields = json.loads(render_relay_payload(record=_record()))
    fields["observation"]["status"] = "acknowledged"

    assert parse_relay_payload(text=json.dumps(fields)) is None


@pytest.mark.parametrize("text", ["not json at all", '"a string"'])
def test_a_payload_that_is_not_a_json_object_reads_as_no_record(text: str) -> None:
    """Both halves: text that will not decode, and text that decodes to a non-object."""
    assert parse_relay_payload(text=text) is None


def test_the_newest_observation_of_one_relay_is_the_one_selected() -> None:
    """A relay accumulates observations; the live one is the last recorded."""
    older = _record(operation_id="op-1")
    newer = _record(operation_id="op-2", met=True)
    other = _record(relay_id="relay-9", operation_id="op-3")

    assert latest_relay(records=(older, other, newer), relay_id=_RELAY) == newer
    assert latest_relay(records=(other,), relay_id=_RELAY) is None


def test_an_operation_identity_resolves_to_the_act_that_first_carried_it() -> None:
    """A retry is answered with what ITS act recorded, never with a later one."""
    first = _record(operation_id="op-1")
    impostor = _record(operation_id="op-1", met=True)

    assert recorded_operation(records=(first, impostor), operation_id="op-1") == first
    assert recorded_operation(records=(first,), operation_id="op-2") is None

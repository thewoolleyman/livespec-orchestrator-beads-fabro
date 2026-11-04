"""The relay record VALUE: its three legs and the two selections over it.

The integration tier binds Scenario 149 end to end and
`test_plan_relay_payload.py` covers the wire form. This module covers the record
itself: which combinations of legs permit a transfer, and which record a retry
and a recheck each resolve to.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    DELIVERY_DELIVERED,
    DELIVERY_UNDELIVERED,
    RelayLegs,
    RelayRecord,
    latest_relay,
    recorded_operation,
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

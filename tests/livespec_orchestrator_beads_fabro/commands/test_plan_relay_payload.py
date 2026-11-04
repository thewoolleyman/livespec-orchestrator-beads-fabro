"""The relay record's WIRE FORM: its comment body and its canonical payload.

Its sibling `test_plan_relay_record.py` covers the VALUE. This module covers the
round trip a retry and a recheck read a relay back through, and every malformed
shape that must fail closed rather than reconstruct a partial record.
"""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_relay_payload import (
    parse_relay_payload,
    payload_line,
    relay_event_body,
    render_relay_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    DELIVERY_UNDELIVERED,
    RelayLegs,
    RelayRecord,
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


def _record(*, met: bool = False, superseded: str | None = None) -> RelayRecord:
    observation = _observation(met=met)
    return RelayRecord(
        relay_id=_RELAY,
        operation_id="op-1",
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


def _mutated(*, change: dict[str, object]) -> str:
    fields = json.loads(render_relay_payload(record=_record()))
    fields.update(change)
    return json.dumps(fields)


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

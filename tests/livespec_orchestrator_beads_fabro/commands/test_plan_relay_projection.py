"""The relay's durable projection: one `plan-relay-event` comment, read back."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro.commands._plan_relay_payload import PLAN_RELAY_PREFIX
from livespec_orchestrator_beads_fabro.commands._plan_relay_projection import (
    read_relay_records,
    write_relay_event,
)
from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    RelayLegs,
    RelayRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import unsatisfied

_EPIC_ID = "bd-ib-relayepic"


def _record(*, operation_id: str = "op-1") -> RelayRecord:
    return RelayRecord(
        relay_id="relay-1",
        operation_id=operation_id,
        sender="plan-supervisor",
        required_result={"repo": "repo", "item_status": {"item_id": "bd-ib-target"}},
        result_identity="repo item_status bd-ib-target status done",
        original_deadline="2026-10-20T18:00:00Z",
        delivered=False,
        legs=RelayLegs(receipt_ack=None, peer_recorded=None, target_evidence=None),
        observation=unsatisfied(
            repo="repo",
            target="repo item_status bd-ib-target status done",
            source="ledger",
            now="2026-10-20T09:00:00Z",
            evidence="bd-ib-target at status active",
            detail="the item does not stand at the expected status",
        ),
        recorded_at="2026-10-20T09:00:00Z",
    )


def _seeded() -> FakeBeadsClient:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="plan",
            description="anchor",
            assignee=None,
            created_at="2026-10-20T08:00:00Z",
            metadata={"rank": "a0"},
        )
    )
    return client


def test_a_written_relay_event_reads_back_as_the_record_that_was_written() -> None:
    """The ledger is the durable store, so the write and the read are one format."""
    client = _seeded()
    record = _record()

    write_relay_event(client=client, epic_id=_EPIC_ID, record=record)

    assert read_relay_records(client=client, epic_id=_EPIC_ID) == (record,)


def test_the_event_is_authored_as_the_sender_that_still_owes_the_obligation() -> None:
    """An expiry falls to the sender, so the timeline has to say who that is."""
    client = _seeded()

    write_relay_event(client=client, epic_id=_EPIC_ID, record=_record())

    text = client.list_comments(issue_id=_EPIC_ID)[0]["text"]
    assert isinstance(text, str)
    assert text.startswith(f"{PLAN_RELAY_PREFIX}\nauthor: plan-supervisor\n")


def test_comments_that_are_not_relay_events_and_unparseable_ones_are_both_dropped() -> None:
    """Dropping an unreadable record makes a retry re-observe, which is the safe way.

    Carrying a half-read one forward would answer the retry with an observation
    this reader assembled. A foreign comment is dropped for the ordinary reason:
    the epic's timeline carries handoffs, scope events and progress events too.
    """
    client = _seeded()
    client.add_comment(issue_id=_EPIC_ID, body="plan-handoff-entry\nauthor: a\n\nbody")
    client.add_comment(
        issue_id=_EPIC_ID,
        body=f"{PLAN_RELAY_PREFIX}\nauthor: a\ntimestamp: t\n\nrelay: relay-1\npayload: {{",
    )
    client.add_comment(
        issue_id=_EPIC_ID,
        body=f"{PLAN_RELAY_PREFIX}\nauthor: a\ntimestamp: t\n\nrelay: relay-1",
    )
    write_relay_event(client=client, epic_id=_EPIC_ID, record=_record(operation_id="op-2"))

    read = read_relay_records(client=client, epic_id=_EPIC_ID)

    assert tuple(record.operation_id for record in read) == ("op-2",)

"""The durable projection of a relay: its `plan-relay-event` comments on the epic.

The relay clause of `contracts.md` makes the ledger the only place a relay's
obligation lives — "Messages with no durable target effect remain unfulfilled" —
so a relay the primitive returned but never appended is an obligation no
independent consumer can discover. This module is the one write and the one read
of those comments.

WHY A RECORD THAT WILL NOT PARSE IS DROPPED RATHER THAN SURFACED. The three
decisions this feeds — a retry's recovery of its own observation, a recheck's
recovery of the original deadline, and the conflicting-target refusal — are each
about what WAS recorded, and an unparseable comment records nothing any of them
can act on. Dropping it makes the retry re-observe and re-record, which is the
safe direction; carrying a half-read record forward would answer a retry with an
observation this reader assembled.

WHY THE READ IS NOT FILTERED BY RELAY ID HERE. One pass over the epic's comments
answers all three questions, and the selections (`latest_relay`,
`recorded_operation`) are pure functions over the result. A per-question read
would be three passes whose answers could disagree with each other, because each
would see the comment list as it stood at a different moment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_relay_record import (
    PLAN_RELAY_PREFIX,
    RelayRecord,
    parse_relay_payload,
    payload_line,
    relay_event_body,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import plan_comment_body

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "read_relay_records",
    "write_relay_event",
]

_TEXT_FIELD = "text"


def write_relay_event(*, client: BeadsClient, epic_id: str, record: RelayRecord) -> None:
    """Append one recorded relay observation to the epic.

    The comment is authored as the RELAY'S SENDER, which is the party that still
    owes the obligation: a record attributed to anyone else would leave the
    timeline unable to say who an expiry falls to.
    """
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_RELAY_PREFIX,
            author=record.sender,
            now=record.recorded_at,
            body=relay_event_body(record=record),
        ),
    )


def read_relay_records(*, client: BeadsClient, epic_id: str) -> tuple[RelayRecord, ...]:
    """Every relay observation recorded on one epic, oldest first."""
    records: list[RelayRecord] = []
    for comment in client.list_comments(issue_id=epic_id):
        text = comment.get(_TEXT_FIELD)
        if not isinstance(text, str) or not text.startswith(PLAN_RELAY_PREFIX):
            continue
        payload = payload_line(text=text)
        record = None if payload is None else parse_relay_payload(text=payload)
        if record is not None:
            records.append(record)
    return tuple(records)

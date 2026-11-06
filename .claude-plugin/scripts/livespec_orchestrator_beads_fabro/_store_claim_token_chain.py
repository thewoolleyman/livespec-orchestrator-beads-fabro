"""The records a claim-token chain is made of, and where a chain ends.

A claim token's close reason names its successor (contracts.md, "Stranded claim
release" -> "Claim tokens", step 2), so from the token an item names a reader
can walk a CHAIN: token, successor, that successor's successor, until it meets
a token that is open, one whose close reason names nothing (a discarded token,
or one closed outside the protocol), or one it cannot read. The writer protocol
walks one item's chain hop by hop with a takeover wait at each hop
(`_store_claim_tokens`); the attention surface walks every item's chain at once
to find the ones no writer can ever win. Both read the same reasons, so the
reason builders and the successor parser live here, beside the walk.

THE BULK WALK IS ONE `bd show` PER HOP DEPTH, NOT ONE PER ITEM. Token records
are no-history records that no list surface returns, so chains can only be read
through `bd show`, and `needs-attention` reads every non-closed item's chain on
every pass. A read per item was the shape that sent that surface past its
budget (`.ai/local-implementation-close-path.md`); `bd show` takes many ids, so
each depth of every chain is read in one call, and a tenant whose chains are
all one token long costs one call.

A CHAIN END IS NEVER GUESSED. A token the show did not return is
`unobservable`, not absent: `bd show` omits an id it cannot find and exits 0, so
an unreadable server and a missing record look alike here, and neither is
reported as a dead end. A closed token whose reason is not one this protocol
writes is unobservable too: something outside the protocol closed it, and what
it meant is not known. Only a token the protocol DISCARDED, or one whose
successor leads back into the chain, is a dead end, because no writer can reach
an open token through it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import attempt_close

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = [
    "CHAIN_DEAD_END",
    "CHAIN_OPEN",
    "CHAIN_UNOBSERVABLE",
    "ChainEnd",
    "discard_claim_token",
    "is_discard_reason",
    "read_chain_ends",
    "successor_named_by",
    "transition_reason",
]

_CLOSE_REASON_KIND = "claim-token-transition"
_DISCARD_REASON_KIND = "claim-token-discard"
_CLOSED_STATUS = "closed"

# The three states a walk can end in, named for the row and the refusal that read them.
CHAIN_OPEN = "open"
CHAIN_DEAD_END = "dead-end"
CHAIN_UNOBSERVABLE = "unobservable"


@dataclass(frozen=True, kw_only=True)
class ChainEnd:
    """The last token a walk reached, and why it stopped there."""

    token_id: str
    state: str


def transition_reason(*, writer: str, intent: str, successor: str) -> str:
    """The close reason a winner writes: who, why, the successor, and the instant for audit."""
    return json.dumps(
        {
            "kind": _CLOSE_REASON_KIND,
            "writer": writer,
            "intent": intent,
            "successor": successor,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def discard_claim_token(*, client: BeadsClient, token_id: str, writer: str) -> None:
    """Close a token its creator never got to name, with a reason that names no successor."""
    attempt_close(
        client=client,
        token_id=token_id,
        reason=json.dumps(
            {"kind": _DISCARD_REASON_KIND, "writer": writer},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def successor_named_by(*, reason: str | None) -> str | None:
    """The successor a transition close reason names; None for a discard or anything else."""
    parsed = _protocol_reason(reason=reason)
    if parsed is None or parsed.get("kind") != _CLOSE_REASON_KIND:
        return None
    value = parsed.get("successor")
    return value.strip() if isinstance(value, str) and value.strip() != "" else None


def is_discard_reason(*, reason: str | None) -> bool:
    """Whether a close reason is the protocol's own discard, which ends a chain for good."""
    parsed = _protocol_reason(reason=reason)
    return parsed is not None and parsed.get("kind") == _DISCARD_REASON_KIND


def _protocol_reason(*, reason: str | None) -> dict[str, object] | None:
    try:
        parsed = json.loads(reason) if reason is not None else None
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def read_chain_ends(*, client: BeadsClient, token_ids: Iterable[str]) -> dict[str, ChainEnd]:
    """Where the chain from each of `token_ids` ends, read in one show per hop depth."""
    starts = sorted(set(token_ids))
    records: dict[str, BeadsRecord] = {}
    requested: set[str] = set()
    frontier = starts
    while frontier:
        requested.update(frontier)
        for record in client.show_issues(issue_ids=frontier):
            record_id = record.get("id")
            if isinstance(record_id, str):
                records[record_id] = record
        frontier = sorted(
            successor
            for token_id in frontier
            if (successor := _successor_of(records=records, token_id=token_id)) is not None
            and successor not in requested
        )
    return {token_id: _end_of(records=records, token_id=token_id) for token_id in starts}


def _successor_of(*, records: dict[str, BeadsRecord], token_id: str) -> str | None:
    record = records.get(token_id)
    if record is None or record.get("status") != _CLOSED_STATUS:
        return None
    return successor_named_by(reason=_reason_of(record=record))


def _reason_of(*, record: BeadsRecord) -> str | None:
    reason = record.get("close_reason")
    return reason if isinstance(reason, str) else None


def _end_of(*, records: dict[str, BeadsRecord], token_id: str) -> ChainEnd:
    walked: set[str] = set()
    current = token_id
    while True:
        record = records.get(current)
        if record is None:
            return ChainEnd(token_id=current, state=CHAIN_UNOBSERVABLE)
        if record.get("status") != _CLOSED_STATUS:
            return ChainEnd(token_id=current, state=CHAIN_OPEN)
        walked.add(current)
        successor = _successor_of(records=records, token_id=current)
        if successor is None:
            discarded = is_discard_reason(reason=_reason_of(record=record))
            return ChainEnd(
                token_id=current, state=CHAIN_DEAD_END if discarded else CHAIN_UNOBSERVABLE
            )
        if successor in walked:
            return ChainEnd(token_id=current, state=CHAIN_DEAD_END)
        current = successor

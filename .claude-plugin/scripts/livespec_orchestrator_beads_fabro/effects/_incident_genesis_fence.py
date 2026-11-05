"""Verification of a published root against the claim-token close that fenced it.

A fenced genesis record names the dispatch claim token whose server-side close
published its root. The root holds only when that token is closed and its
retained reason is a genesis fence naming the same root, item, repository and
token; a comment alone never establishes authority.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    decode_record,
)
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisFence,
    decode_genesis_fence,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["FENCED_GENESIS_KEYS", "fenced_root_holds", "published_fence"]

FENCED_GENESIS_KEYS = frozenset(
    ("schema", "repository", "item_id", "root_token_id", "claim_token_id")
)


def fenced_root_holds(*, client: BeadsClient, record: dict[str, Any], repository: str) -> bool:
    """A legacy record has no fence; a fenced one holds only when its token's close names it."""
    claim_token_id = record.get("claim_token_id")
    if claim_token_id is None:
        return True
    if not isinstance(claim_token_id, str) or not claim_token_id:
        return False
    token = client.show_issue(issue_id=claim_token_id)
    fence = decode_genesis_fence(reason=token.get("close_reason"))
    return (
        token.get("status") == "closed"
        and fence is not None
        and fence.root_token_id == record["root_token_id"]
        and fence.item_id == record["item_id"]
        and fence.repository == repository
        and fence.expected_claim == claim_token_id
    )


def published_fence(*, client: BeadsClient, item_id: str, root: str) -> GenesisFence | None:
    """The fence behind an already verified published root, or None for an unfenced chain."""
    for comment in client.list_comments(issue_id=item_id):
        record = decode_record(
            text=comment.get("text"), marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS
        )
        if record is not None and record["root_token_id"] == root:
            token = client.show_issue(issue_id=record["claim_token_id"])
            return decode_genesis_fence(reason=token.get("close_reason"))
    return None

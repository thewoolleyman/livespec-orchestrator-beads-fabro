"""Incident genesis records: the request, the retained fence and the receipt.

A first incident authority is published in ONE server-enforced operation: the
conditional close of the canonical item's CURRENT dispatch claim token. Its
close reason is a valid claim-token transition (so every other claim writer
reads it as the protocol's own record) carrying an `incident` block that binds
the absent root being published, the exact expected claim and the immutable
request digest. Winning that close is the only exclusion; a comment, a fixed-id
create, a metadata update or a host-scoped lock never initializes authority.
This module is pure: it decodes, encodes and digests, and writes nothing.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
)
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved
from livespec_orchestrator_beads_fabro._incident_entry import prior_claim_valid
from livespec_orchestrator_beads_fabro.effects import parse_json

__all__: list[str] = [
    "GENESIS_CAPABILITY_UNAVAILABLE",
    "GenesisFence",
    "GenesisReceipt",
    "GenesisRequest",
    "capability_unavailable",
    "claim_successor",
    "decode_genesis_fence",
    "decode_genesis_request",
    "genesis_comment",
    "genesis_fence",
    "genesis_fence_reason",
    "request_digest",
]

GENESIS_CAPABILITY_UNAVAILABLE = "incident-genesis-capability-unavailable"
_REQUEST_KEYS = frozenset(("schema", "principal", "expected_claim", "attempt"))
# The claim-token protocol's own transition record shape: every claim writer
# parses `kind` and `successor`, so a genesis close is never read as foreign.
_CLAIM_TRANSITION_KIND = "claim-token-transition"
_GENESIS_INTENT = "incident-genesis"
_FENCE_TEXT_KEYS = (
    "repository",
    "item_id",
    "operation_id",
    "principal",
    "request_digest",
    "root_token_id",
    "expected_claim",
)
_FENCE_KEYS = frozenset(("schema", *_FENCE_TEXT_KEYS))
# A fence written before entry retained the prior claim row has no such key.
_FENCE_KEY_SETS = (_FENCE_KEYS, _FENCE_KEYS | {"prior_claim"})


@dataclass(frozen=True, kw_only=True)
class GenesisRequest:
    """One immutable initialization request for a canonical incident item."""

    principal: str
    expected_claim: str
    attempt: IncidentAttempt


@dataclass(frozen=True, kw_only=True)
class GenesisFence:
    """The incident block retained on the closed claim token that genesis won."""

    repository: str
    item_id: str
    operation_id: str
    principal: str
    request_digest: str
    root_token_id: str
    expected_claim: str
    successor: str
    # The claim row entry found and fenced: status, assignee and whole dispatch stamp.
    prior_claim: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class GenesisReceipt:
    """A confirmed first publication, read back from the chain it created."""

    request_digest: str
    root_token_id: str
    claim_token_id: str
    successor_claim_token_id: str
    committed_token_id: str
    current_token_id: str
    attempt: IncidentAttempt
    recovered: bool


def _canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _text(*, value: object) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _initial(*, attempt: IncidentAttempt, repository: str, item_id: str, operation_id: str) -> bool:
    return (
        attempt.repository == repository
        and attempt.item_id == item_id
        and attempt.operation_id == operation_id
        and attempt.generation == 1
        and attempt.phase == "repair"
        and isinstance(attempt.carrier, BranchReserved)
    )


def decode_genesis_request(
    *, text: str, repository: str, item_id: str, operation_id: str
) -> GenesisRequest | None:
    """Accept only canonical bytes naming one exact initial branch-reserved snapshot."""
    value = parse_json(text=text)
    if not isinstance(value, dict):
        return None
    row = cast("dict[str, Any]", value)
    if frozenset(row) != _REQUEST_KEYS or type(row["schema"]) is not int or row["schema"] != 1:
        return None
    if _canonical(value=row) != text:
        return None
    if not _text(value=row["principal"]) or not _text(value=row["expected_claim"]):
        return None
    attempt = decode_attempt(value=row["attempt"])
    if attempt is None or not _initial(
        attempt=attempt, repository=repository, item_id=item_id, operation_id=operation_id
    ):
        return None
    return GenesisRequest(
        principal=row["principal"], expected_claim=row["expected_claim"], attempt=attempt
    )


def request_digest(*, request: GenesisRequest) -> str:
    """The SHA-256 of the canonical request bytes; identical retries share it."""
    return hashlib.sha256(
        _canonical(
            value={
                "schema": 1,
                "principal": request.principal,
                "expected_claim": request.expected_claim,
                "attempt": asdict(request.attempt),
            }
        ).encode()
    ).hexdigest()


def capability_unavailable(*, request: GenesisRequest) -> AuthorityRefusal:
    """The named refusal when no all-writer conditional operation is installed."""
    detail = (
        f"{request.attempt.item_id} request sha256:{request_digest(request=request)}: the "
        "installed public ledger offers no server-enforced operation conditioned on an "
        "absent incident root and the exact current claim; no activation or incident "
        "effect was written"
    )
    return AuthorityRefusal(code=GENESIS_CAPABILITY_UNAVAILABLE, detail=detail)


def genesis_fence(
    *,
    request: GenesisRequest,
    root_token_id: str,
    successor: str,
    prior_claim: dict[str, Any] | None = None,
) -> GenesisFence:
    """The fence one genesis attempt retains on the claim token it closes."""
    return GenesisFence(
        repository=request.attempt.repository,
        item_id=request.attempt.item_id,
        operation_id=request.attempt.operation_id,
        principal=request.principal,
        request_digest=request_digest(request=request),
        root_token_id=root_token_id,
        expected_claim=request.expected_claim,
        successor=successor,
        prior_claim=prior_claim,
    )


def genesis_fence_reason(*, fence: GenesisFence, closed_at: str) -> str:
    """The close reason that publishes a root and rotates the claim in one record."""
    return _canonical(
        value={
            "kind": _CLAIM_TRANSITION_KIND,
            "writer": fence.principal,
            "intent": _GENESIS_INTENT,
            "successor": fence.successor,
            "closed_at": closed_at,
            "incident": {
                "schema": 1,
                "repository": fence.repository,
                "item_id": fence.item_id,
                "operation_id": fence.operation_id,
                "principal": fence.principal,
                "request_digest": fence.request_digest,
                "root_token_id": fence.root_token_id,
                "expected_claim": fence.expected_claim,
                "prior_claim": fence.prior_claim,
            },
        }
    )


def _transition(*, reason: object) -> dict[str, Any] | None:
    if not isinstance(reason, str):
        return None
    value = parse_json(text=reason)
    if not isinstance(value, dict):
        return None
    row = cast("dict[str, Any]", value)
    if row.get("kind") != _CLAIM_TRANSITION_KIND or not _text(value=row.get("successor")):
        return None
    return row


def claim_successor(*, reason: object) -> str | None:
    """The successor a closed claim token names, under any writer's intent."""
    row = _transition(reason=reason)
    return None if row is None else cast("str", row["successor"])


def decode_genesis_fence(*, reason: object) -> GenesisFence | None:
    """Decode a genesis close exactly; any other close reason is not a fence."""
    row = _transition(reason=reason)
    if row is None or row.get("intent") != _GENESIS_INTENT:
        return None
    block = row.get("incident")
    if not isinstance(block, dict):
        return None
    fence = cast("dict[str, Any]", block)
    if frozenset(fence) not in _FENCE_KEY_SETS or fence["schema"] != 1:
        return None
    if not all(_text(value=fence[key]) for key in _FENCE_TEXT_KEYS):
        return None
    if not prior_claim_valid(value=fence.get("prior_claim")):
        return None
    return GenesisFence(
        repository=fence["repository"],
        item_id=fence["item_id"],
        operation_id=fence["operation_id"],
        principal=fence["principal"],
        request_digest=fence["request_digest"],
        root_token_id=fence["root_token_id"],
        expected_claim=fence["expected_claim"],
        successor=row["successor"],
        prior_claim=fence.get("prior_claim"),
    )


def genesis_comment(
    *, repository: str, item_id: str, root_token_id: str, claim_token_id: str
) -> str:
    """The published genesis record, naming the claim token whose close fenced it."""
    return GENESIS_MARKER + _canonical(
        value={
            "schema": 1,
            "repository": repository,
            "item_id": item_id,
            "root_token_id": root_token_id,
            "claim_token_id": claim_token_id,
        }
    )

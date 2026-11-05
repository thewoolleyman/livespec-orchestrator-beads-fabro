"""Incident genesis: the first authority publication, refused without capability.

A first incident authority must be published in ONE server-enforced operation
conditioned on an absent incident root AND the exact current claim. The public
ledger boundary installed today offers no such operation: a conditional close
binds one record, a create is unconditional, a fixed-id create is an upsert and
a metadata update is a client read-modify-write. Until a claim-token protocol in
which every applicable writer participates provides it, genesis returns the
named `incident-genesis-capability-unavailable` refusal. It writes nothing,
files no other item and takes no local lock, so a refusal can never be mistaken
for authority. The request is still decoded and bound, so the refusal names the
exact request an operator asked for.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
)
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved
from livespec_orchestrator_beads_fabro.effects import parse_json

__all__: list[str] = [
    "GENESIS_CAPABILITY_UNAVAILABLE",
    "GenesisRequest",
    "decode_genesis_request",
    "publish_genesis",
]

GENESIS_CAPABILITY_UNAVAILABLE = "incident-genesis-capability-unavailable"
_REQUEST_KEYS = frozenset(("schema", "principal", "expected_claim", "attempt"))


@dataclass(frozen=True, kw_only=True)
class GenesisRequest:
    """One immutable initialization request for a canonical incident item."""

    principal: str
    expected_claim: str
    attempt: IncidentAttempt


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


def publish_genesis(*, request: GenesisRequest) -> AuthorityRefusal:
    """Refuse first publication by name; no installed provider offers the exclusion."""
    digest = hashlib.sha256(
        _canonical(
            value={
                "schema": 1,
                "principal": request.principal,
                "expected_claim": request.expected_claim,
                "attempt": asdict(request.attempt),
            }
        ).encode()
    ).hexdigest()
    detail = (
        f"{request.attempt.item_id} request sha256:{digest}: the installed public ledger "
        "offers no server-enforced operation conditioned on an absent incident root and "
        "the exact current claim; no activation or incident effect was written"
    )
    return AuthorityRefusal(code=GENESIS_CAPABILITY_UNAVAILABLE, detail=detail)

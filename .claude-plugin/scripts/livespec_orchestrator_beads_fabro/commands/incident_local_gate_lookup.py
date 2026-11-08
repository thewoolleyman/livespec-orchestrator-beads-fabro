"""Read immutable partial evidence through the current canonical incident identity."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from returns.io import impure_safe
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import (
    MARKER,
    current_receipt_authority,
    decode_receipt,
    matching_receipts,
    receipt_body,
    receipt_mapping,
)
from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading

__all__: list[str] = ["LocalGateLookup", "read_local_gates"]


@dataclass(frozen=True, kw_only=True)
class LocalGateLookup:
    """Exact recorded evidence or authoritative absence, never effect authority."""

    status: Literal["recorded", "absent"]
    receipt_id: str
    committed_token_id: str
    current_token_id: str
    checksum: str | None = None
    receipt: dict[str, Any] | None = None


@impure_safe
def _lookup(
    *, client: BeadsClient, observed: IncidentReading, receipt_id: str
) -> LocalGateLookup | AuthorityRefusal:
    if not receipt_id.strip() or receipt_id != receipt_id.strip():
        return AuthorityRefusal(code="incident-receipt-invalid", detail=receipt_id)
    standing = current_receipt_authority(client=client, observed=observed)
    if isinstance(standing, AuthorityRefusal):
        return standing
    matches = matching_receipts(client=client, observed=observed, receipt_id=receipt_id)
    if len(matches) > 1:
        return AuthorityRefusal(code="incident-receipt-readback-conflict", detail=receipt_id)
    receipt: dict[str, Any] | None = None
    checksum: str | None = None
    if matches:
        body = next(iter(matches))
        record = receipt_mapping(value=parse_json(text=body[len(MARKER) :]))
        receipt = decode_receipt(
            text=json.dumps(record.get("receipt"), sort_keys=True, separators=(",", ":")),
            observed=observed,
        )
        if receipt is None or body != receipt_body(observed=observed, receipt=receipt):
            return AuthorityRefusal(code="incident-receipt-identity-conflict", detail=receipt_id)
        checksum = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    standing = current_receipt_authority(client=client, observed=observed)
    if isinstance(standing, AuthorityRefusal):
        return standing
    return LocalGateLookup(
        status="recorded" if receipt is not None else "absent",
        receipt_id=receipt_id,
        committed_token_id=observed.committed_token_id,
        current_token_id=observed.current_token_id,
        checksum=checksum,
        receipt=receipt,
    )


def read_local_gates(
    *, client: BeadsClient, observed: IncidentReading, receipt_id: str
) -> LocalGateLookup | AuthorityRefusal:
    """Unknown reads refuse; an absent local file never supplies absence."""
    result = _lookup(client=client, observed=observed, receipt_id=receipt_id)
    if not is_successful(result):
        return AuthorityRefusal(
            code="incident-receipt-unavailable", detail=str(unsafe_perform_io(result.failure()))
        )
    return unsafe_perform_io(result.unwrap())

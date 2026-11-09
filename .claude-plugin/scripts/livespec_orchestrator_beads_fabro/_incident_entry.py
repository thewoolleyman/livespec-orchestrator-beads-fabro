"""Canonical incident entry records: the minimal filing, the retained takeover, the bindings.

Entry keeps ONE canonical item. A scope no item covers is filed minimally,
with its impact, owner, scope and behavioral intent, and ordinary admission and
spec debt recorded as deferred to normal repayment; an identified item is
reused. Host ownership is taken through the item's current claim token, the
same server-enforced close every factory writer serializes on, and the one
guarded write that follows carries what this module builds: the incident
holder stamp that every factory predicate reads as another claim, and the
retained record of the prior claim, the invalidating generation and the
unobserved cancellation. This module is pure: it encodes, decodes, digests
and selects, and writes nothing.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import (
    CARRIER_UNSUPPORTED,
    BranchReserved,
    PrBound,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    ClaimStamp,
    claim_stamp_metadata,
)
from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord

__all__: list[str] = [
    "ENTRY_LABEL",
    "ENTRY_MARKER",
    "FILING_METADATA_KEY",
    "GENERATION_STALE",
    "HOLDER_DISPATCH_PREFIX",
    "INCIDENT_CLAIM_METADATA_KEY",
    "CarrierSelection",
    "FilingReceipt",
    "FilingRequest",
    "decode_filing_request",
    "deferred_admission_comment",
    "filing_description",
    "filing_digest",
    "filing_identity",
    "filing_metadata",
    "incident_claim_decided",
    "prior_claim",
    "prior_claim_valid",
    "select_carrier",
    "takeover_metadata",
]

ENTRY_MARKER = "livespec-incident-entry-v1\n"
ENTRY_LABEL = "incident:entry"
INCIDENT_CLAIM_METADATA_KEY = "incident_claim"
FILING_METADATA_KEY = "incident_filing"
GENERATION_STALE = "incident-generation-stale"
# The holder stamp's dispatch and run ids carry this prefix; no factory dispatch id does.
HOLDER_DISPATCH_PREFIX = "incident:"
_DEFERRED_TO_REPAYMENT = ("ordinary-admission", "spec-debt")
_FILING_TEXT_KEYS = (
    "repository",
    "principal",
    "operation_id",
    "title",
    "impact",
    "scope",
    "behavioral_intent",
)
_FILING_KEYS = frozenset(("schema", *_FILING_TEXT_KEYS))
_PRIOR_CLAIM_KEYS = frozenset(("status", "assignee", "dispatch_claim"))


@dataclass(frozen=True, kw_only=True)
class FilingRequest:
    """One minimal canonical incident filing: impact, owner, scope and intent."""

    repository: str
    principal: str
    operation_id: str
    title: str
    impact: str
    scope: str
    behavioral_intent: str


@dataclass(frozen=True, kw_only=True)
class FilingReceipt:
    """The one identity a filing established, with the claim entry will consume."""

    item_id: str
    claim_token_id: str
    request_digest: str
    recovered: bool


@dataclass(frozen=True, kw_only=True)
class CarrierSelection:
    """The exact carrier a current attempt names; a PR number only once `pr-bound`."""

    state: str
    target_ref: str
    remote_head: str | None
    pr_number: int | None


def _canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _text(*, value: object) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _text_or_none(*, value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}


def decode_filing_request(*, text: str) -> FilingRequest | None:
    """Accept only canonical bytes naming every filing field, none of them blank."""
    value = parse_json(text=text)
    if not isinstance(value, dict):
        return None
    row = cast("dict[str, Any]", value)
    if frozenset(row) != _FILING_KEYS or type(row["schema"]) is not int or row["schema"] != 1:
        return None
    if _canonical(value=row) != text or not all(_text(value=row[k]) for k in _FILING_TEXT_KEYS):
        return None
    return FilingRequest(**{key: row[key] for key in _FILING_TEXT_KEYS})


def filing_digest(*, request: FilingRequest) -> str:
    """The SHA-256 of the canonical filing bytes; an identical retry shares it."""
    return hashlib.sha256(_canonical(value={"schema": 1, **asdict(request)}).encode()).hexdigest()


def filing_description(*, request: FilingRequest) -> str:
    """The filed item's body: the four facts entry records without slow judgement."""
    return (
        "Incident filed by canonical entry. Ordinary model-backed admission and spec "
        "debt are deferred to normal repayment on this same item.\n\n"
        f"## Impact\n\n{request.impact}\n\n"
        f"## Scope\n\n{request.scope}\n\n"
        f"## Behavioral intent\n\n{request.behavioral_intent}\n\n"
        f"## Owner\n\n{request.principal}\n"
    )


def filing_metadata(*, request: FilingRequest) -> dict[str, Any]:
    """The identity the filed item carries so an exact retry recovers it."""
    return {
        FILING_METADATA_KEY: {
            "schema": 1,
            "operation_id": request.operation_id,
            "principal": request.principal,
            "request_digest": filing_digest(request=request),
        }
    }


def filing_identity(*, record: BeadsRecord) -> tuple[str, str] | None:
    """The (operation id, request digest) a filed item records, or None for any other item."""
    raw = _metadata_of(record=record).get(FILING_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    row = cast("dict[str, Any]", raw)
    operation_id, digest = row.get("operation_id"), row.get("request_digest")
    if not _text(value=operation_id) or not _text(value=digest):
        return None
    return cast("str", operation_id), cast("str", digest)


def deferred_admission_comment(*, item_id: str, operation_id: str, principal: str) -> str:
    """The retained record that ordinary admission and spec debt are owed at repayment."""
    return ENTRY_MARKER + _canonical(
        value={
            "schema": 1,
            "item_id": item_id,
            "operation_id": operation_id,
            "principal": principal,
            "deferred_to_repayment": list(_DEFERRED_TO_REPAYMENT),
        }
    )


def prior_claim(*, record: BeadsRecord) -> dict[str, Any]:
    """The claim row entry found: status, assignee and the whole dispatch stamp."""
    stamp = _metadata_of(record=record).get(CLAIM_STAMP_METADATA_KEY)
    return {
        "status": _text_or_none(value=record.get("status")),
        "assignee": _text_or_none(value=record.get("assignee")),
        "dispatch_claim": dict(cast("dict[str, Any]", stamp)) if isinstance(stamp, dict) else None,
    }


def prior_claim_valid(*, value: object) -> bool:
    """A retained prior claim is absent, or exactly the three facts `prior_claim` records."""
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    row = cast("dict[str, Any]", value)
    return frozenset(row) == _PRIOR_CLAIM_KEYS and all(
        row[key] is None or isinstance(row[key], str) for key in ("status", "assignee")
    )


def takeover_metadata(
    *,
    operation_id: str,
    generation: int,
    owner: str,
    principal: str,
    root_token_id: str,
    prior: dict[str, Any] | None,
) -> dict[str, Any]:
    """The metadata overlay of the one guarded write that takes host ownership.

    The holder stamp replaces the factory's whole `dispatch_claim` object: it
    names the operation as its dispatch and the authority root as its run, so
    no factory predicate reads the row as unstamped, pending or its own. The
    prior row is retained beside it, with the cancellation it did not observe.
    """
    stamp = ClaimStamp(
        dispatch_id=f"{HOLDER_DISPATCH_PREFIX}{operation_id}",
        dispatching_host=principal,
        run_id=f"{HOLDER_DISPATCH_PREFIX}{root_token_id}",
        factory_name=None,
        factory_server=None,
    )
    return claim_stamp_metadata(stamp=stamp) | {
        INCIDENT_CLAIM_METADATA_KEY: {
            "schema": 1,
            "operation_id": operation_id,
            "generation": generation,
            "owner": owner,
            "prior_claim": prior,
            "factory_cancel": "unobserved",
            "deferred_to_repayment": list(_DEFERRED_TO_REPAYMENT),
        }
    }


def incident_claim_decided(
    *, operation_id: str, generation: int, owner: str
) -> Callable[[BeadsRecord], bool]:
    """The decision an incident claim writer rests on: this entry still holds the item.

    Asked of the record a token-guarded write is based on, so a write made
    after ownership moved to another operation, generation or owner answers
    `claim-changed` and lands nothing.
    """

    return lambda record: _claim_held(
        record=record, operation_id=operation_id, generation=generation, owner=owner
    )


def _claim_held(*, record: BeadsRecord, operation_id: str, generation: int, owner: str) -> bool:
    raw = _metadata_of(record=record).get(INCIDENT_CLAIM_METADATA_KEY)
    if not isinstance(raw, dict):
        return False
    claim = cast("dict[str, Any]", raw)
    held = claim.get("generation")
    return (
        claim.get("operation_id") == operation_id
        and type(held) is int
        and held == generation
        and claim.get("owner") == owner
    )


def select_carrier(*, reading: IncidentReading) -> CarrierSelection | AuthorityRefusal:
    """The exact carrier of a reading the caller has already confirmed current."""
    carrier = reading.attempt.carrier
    if carrier is None:
        return AuthorityRefusal(code=CARRIER_UNSUPPORTED, detail=reading.attempt.item_id)
    return CarrierSelection(
        state=carrier.state,
        target_ref=carrier.target_ref,
        remote_head=None if isinstance(carrier, BranchReserved) else carrier.remote_head,
        pr_number=reading.attempt.pr_number if isinstance(carrier, PrBound) else None,
    )

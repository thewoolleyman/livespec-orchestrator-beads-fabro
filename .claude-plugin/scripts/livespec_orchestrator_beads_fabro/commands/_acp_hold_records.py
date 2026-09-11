"""One VERSIONED observed-availability record: its shape, id, and expiry.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A current record carries at least `scope`, opaque `hold_key`,
optional `candidate_key`, stable `observation_id`, occurrence time,
bounded expiry, and explicit `schema_version: 1`. Unknown versions MUST
be preserved and surfaced as unobservable, never interpreted as v1,
rewritten, or allowed to mint a hold."

THE WRITER TAKES NO CLOCK, AND THAT IS THE POINT. "Expiry is computed
from occurrence time and never from ingestion." A builder that could read
`utc_now_iso()` would let a replayed projection push a hold forward
every time reconciliation ran, which is the failure the clause names.
`hold_observation_record` is handed `occurred_at` and derives `expires_at`
from it alone; there is no parameter it could use instead.

THE EVIDENCE KIND IS A CLOSED SET FOR THE SAME REASON. "A hold MUST come
from an actual candidate attempt: a typed terminal failure or an
idempotently projected `agent.acp.failover` event ... No hold may come
from credentials, catalogs, host probes, predicted health, price, model
strength, or provider reset claims." There is no evidence kind for a
probe, so the admission-time credential probe -- which the same section
says "creates no observed record" -- has nothing to pass.

THE OBSERVATION ID IS A DIGEST OF THE EVIDENCE PLUS THE SCOPE IT LANDS
ON, never a counter or a timestamp. Re-ingesting the same failover event
therefore produces the identical id, which is what makes the ledger's
first-write-wins dedupe idempotent; and one event that legitimately
covers two different scopes still yields two distinct records.

BOUNDED EXPIRY MATCHES THE LEGACY PROVIDER RECORD'S FIFTEEN MINUTES
deliberately. The two valves observe the same kind of outage on the same
factory, and a typed hold that outlived its legacy counterpart would make
the migration path visible to operators as a behaviour change nobody
ratified.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    CANDIDATE_SCOPE,
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "HOLD_EVIDENCE_KINDS",
    "HOLD_INTERVAL",
    "HOLD_SCHEMA_VERSION",
    "HOLD_STAGE",
    "AcpAvailabilityHold",
    "hold_expired",
    "hold_observation_record",
    "observation_id",
    "parse_hold_instant",
    "parse_hold_record",
]

HOLD_SCHEMA_VERSION = 1
HOLD_STAGE = "acp-availability-observed"

# The only two things that count as an actual candidate attempt.
HOLD_EVIDENCE_KINDS: tuple[str, ...] = ("acp-failover-event", "candidate-attempt")

HOLD_INTERVAL = timedelta(minutes=15)

_ID_LENGTH = 24
_ID_PREFIX = "acpobs-"
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The digest separator is a byte no opaque key can contain, so the
# concatenation is unambiguous. A printable one -- a space, a colon --
# would let two different key tuples flatten to the same material and
# therefore to the same observation id.
_ID_SEPARATOR = "\x00"


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilityHold:
    """One live schema-v1 observation, exactly as the contract enumerates it."""

    schema_version: int
    observation_id: str
    scope: str
    hold_key: str
    candidate_key: str | None
    cause: str
    occurred_at: str
    expires_at: str

    @property
    def target(self) -> tuple[str, str, str | None]:
        """The exact `(scope, hold_key, candidate_key)` this record holds.

        Clearance and success retirement both address a record by this
        triple rather than by observation id: an operator knows which
        entitlement is back, not which digest recorded it.
        """
        return (self.scope, self.hold_key, self.candidate_key)


def observation_id(*, evidence_kind: str, evidence_id: str, failure: AcpAvailabilityFailure) -> str:
    """The STABLE id re-ingesting the same evidence reproduces exactly.

    The scope triple is digested alongside the evidence because one
    failover event can legitimately land on a domain and a candidate
    record; keying on the evidence alone would collapse them into one.
    """
    material = _ID_SEPARATOR.join(
        (
            evidence_kind,
            evidence_id,
            failure.scope,
            failure.hold_key,
            failure.candidate_key or "",
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:_ID_LENGTH]
    return f"{_ID_PREFIX}{digest}"


def hold_observation_record(
    *,
    failure: AcpAvailabilityFailure,
    evidence_kind: str,
    evidence_id: str,
    occurred_at: str,
    work_item_id: str,
    node: str,
) -> dict[str, object] | str:
    """Build one appendable v1 observation, or refuse naming what is wrong.

    Refusing an evidence kind outside the closed set is what keeps a
    credential probe, a catalog read or a provider's own reset claim from
    minting a hold: there is no spelling of those that this function
    accepts.
    """
    if evidence_kind not in HOLD_EVIDENCE_KINDS:
        return (
            f"evidence kind {evidence_kind!r} cannot mint an availability hold; "
            f"a hold comes only from {', '.join(HOLD_EVIDENCE_KINDS)}"
        )
    if evidence_id.strip() == "":
        return "evidence id must be non-empty; a hold with no evidence identifies no attempt"
    occurred = parse_hold_instant(text=occurred_at)
    if occurred is None:
        return f"occurrence time {occurred_at!r} is not an ISO-8601 instant"
    return {
        "stage": HOLD_STAGE,
        "schema_version": HOLD_SCHEMA_VERSION,
        "observation_id": observation_id(
            evidence_kind=evidence_kind, evidence_id=evidence_id, failure=failure
        ),
        "scope": failure.scope,
        "hold_key": failure.hold_key,
        "candidate_key": failure.candidate_key,
        "cause": failure.cause,
        "evidence_kind": evidence_kind,
        "evidence_id": evidence_id,
        "occurred_at": occurred_at,
        "expires_at": (occurred + HOLD_INTERVAL).strftime(_ISO_FORMAT),
        "work_item_id": work_item_id,
        "node": node,
    }


def parse_hold_record(*, record: Mapping[str, Any]) -> AcpAvailabilityHold | str:
    """Read one stored observation, or say why it is UNOBSERVABLE.

    A refusal string here never means "discard": the ledger keeps the raw
    record and surfaces it, which is the contract's "preserved and
    surfaced as unobservable". The version check runs FIRST, so no later
    check ever reads an unknown version's fields on v1's meanings.
    """
    for check in (_version_refusal, _scope_refusal, _text_refusal, _candidate_key_refusal):
        refusal = check(record=record)
        if refusal is not None:
            return refusal
    candidate_key = record.get("candidate_key")
    return AcpAvailabilityHold(
        schema_version=HOLD_SCHEMA_VERSION,
        observation_id=str(record["observation_id"]),
        scope=str(record["scope"]),
        hold_key=str(record["hold_key"]),
        candidate_key=candidate_key if isinstance(candidate_key, str) else None,
        cause=str(record["cause"]),
        occurred_at=str(record["occurred_at"]),
        expires_at=str(record["expires_at"]),
    )


def _version_refusal(*, record: Mapping[str, Any]) -> str | None:
    """Refuse any version but exactly 1.

    An equality test rather than a floor, because "never interpreted as
    v1" forbids reading a v2 record on v1's field meanings -- including a
    v2 that happens to spell every v1 field the same way.
    """
    version = record.get("schema_version")
    if version != HOLD_SCHEMA_VERSION:
        return f"unknown observation schema_version {version!r}"
    return None


def _scope_refusal(*, record: Mapping[str, Any]) -> str | None:
    """Refuse a scope outside the two ratified values."""
    scope = record.get("scope")
    if scope not in (DOMAIN_SCOPE, CANDIDATE_SCOPE):
        return f"unknown observation scope {scope!r}"
    return None


def _text_refusal(*, record: Mapping[str, Any]) -> str | None:
    """Refuse a missing text field or an unreadable instant pair."""
    if _required_text(record=record, names=("observation_id", "hold_key", "cause")) is None:
        return "observation is missing a required text field"
    instants = _required_text(record=record, names=("occurred_at", "expires_at"))
    if instants is None or any(parse_hold_instant(text=text) is None for text in instants):
        return "observation carries no readable occurrence time and bounded expiry"
    return None


def _candidate_key_refusal(*, record: Mapping[str, Any]) -> str | None:
    """Refuse a candidate key that disagrees with the record's own scope."""
    candidate_key = record.get("candidate_key")
    if record.get("scope") == CANDIDATE_SCOPE and not isinstance(candidate_key, str):
        return "a candidate-scoped observation must name its candidate_key"
    if record.get("scope") == DOMAIN_SCOPE and candidate_key is not None:
        return "a domain-scoped observation must not name a candidate_key"
    return None


def hold_expired(*, hold: AcpAvailabilityHold, now_iso: str) -> bool:
    """Whether this record's bounded expiry has already elapsed.

    An unreadable `now` reports NOT expired, which keeps the hold
    standing. `parse_hold_record` has already proved the record's own
    instants readable, so the only way here is a caller passing a
    malformed clock -- and dropping a live provider hold because the
    caller's clock could not be read would send work at an outage.
    """
    expiry = parse_hold_instant(text=hold.expires_at)
    now = parse_hold_instant(text=now_iso)
    if expiry is None or now is None:
        return False
    return expiry <= now


def parse_hold_instant(*, text: str) -> datetime | None:
    """One journal instant as a datetime, or `None` when it is unreadable."""
    parsed = parse_iso_datetime(text=text.removesuffix("Z") + "+00:00")
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    return parsed


def _required_text(*, record: Mapping[str, Any], names: tuple[str, ...]) -> tuple[str, ...] | None:
    """Every named field as non-blank text, or `None` when one is missing."""
    values: list[str] = []
    for name in names:
        value = record.get(name)
        if not isinstance(value, str) or value.strip() == "":
            return None
        values.append(value)
    return tuple(values)

"""Decode the canonical JSON payloads the incident-authority lifecycle actions take.

Every JSON payload must be the canonical encoding (sorted keys, compact
separators) of exactly its record's fields; anything else is the named refusal
`incident-action-invalid-payload` and nothing is written.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any, TypeVar, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
)
from livespec_orchestrator_beads_fabro.effects import parse_json

__all__: list[str] = [
    "INVALID_PAYLOAD",
    "decode_attributed_attempt",
    "decode_record",
    "invalid_payload",
]

INVALID_PAYLOAD = "incident-action-invalid-payload"
_SCALARS: dict[str, type] = {"str": str, "bool": bool}
_T = TypeVar("_T")


def invalid_payload(*, flag: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=INVALID_PAYLOAD, detail=f"{flag}: {detail}")


def _canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def decode_record(*, text: str, shape: type[_T], flag: str) -> _T | AuthorityRefusal:
    """Decode exactly one record of `shape` from its canonical JSON, or refuse."""
    raw = parse_json(text=text)
    names = {field.name: _SCALARS.get(str(field.type)) for field in fields(cast("Any", shape))}
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else None
    if value is None or text != _canonical(value=value):
        return invalid_payload(flag=flag, detail="not one canonical JSON object")
    if set(value) != set(names) or any(type(value[k]) is not t for k, t in names.items()):
        return invalid_payload(flag=flag, detail=f"needs exactly {sorted(names)} with their types")
    return shape(**value)


def decode_attributed_attempt(*, text: str) -> IncidentAttempt | AuthorityRefusal:
    """The attributed attempt in its canonical record bytes; the library re-reads the chain."""
    raw = parse_json(text=text)
    attempt = decode_attempt(value=raw)
    if attempt is None or text != _canonical(value=attempt_record(attempt=attempt)):
        return invalid_payload(flag="--attributed-json", detail="not one canonical attempt record")
    return attempt

"""The private host file one Codex identity observation is remembered in.

The persistence half of the opt-in credential observation. A refresh happens
between two runs of a status command, so the only way a status reading can say
anything about it is to have remembered the preceding reading.

What is stored is deliberately narrow: the one-way fingerprints
`_dispatcher_codex_identity_claims` produced, plus the access token's expiry
instant and the moment of the reading. No token, no claim value, and nothing
copied out of `auth.json` -- the provider's authentication file is only ever
read, and never by this module at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "IDENTITY_STATE_SCHEMA",
    "CodexIdentityStateRecord",
    "PriorIdentityState",
    "read_prior_identity_state",
    "write_identity_state",
]

# Versioned, so a later field addition is a schema a reader can recognise
# rather than a shape it has to guess at.
IDENTITY_STATE_SCHEMA = "livespec-codex-identity-observation/v1"

_SCHEMA_FIELD = "schema"
_OBSERVED_AT_FIELD = "observed_at_epoch"
_EXPIRES_AT_FIELD = "expires_at_epoch"
_TOKEN_FIELD = "token_fingerprint"  # noqa: S105 - a JSON field NAME; its value is a digest

PriorStateStatus = Literal["absent", "readable"]


@dataclass(frozen=True, kw_only=True)
class CodexIdentityStateRecord:
    """One remembered observation, exactly as the state file carries it."""

    token_fingerprint: str | None
    expires_at_epoch: int | None
    observed_at_epoch: int


@dataclass(frozen=True, kw_only=True)
class PriorIdentityState:
    """The preceding observation, and what reading it actually established."""

    status: PriorStateStatus
    detail: str
    record: CodexIdentityStateRecord | None


def read_prior_identity_state(*, path: Path) -> PriorIdentityState:
    """Read the preceding observation out of the private state file."""
    stored = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(stored, AttemptFailure):
        return PriorIdentityState(
            status="absent",
            detail="No preceding observation has been recorded at this path.",
            record=None,
        )
    raw = parse_json(text=stored)
    if isinstance(raw, JsonParseFailure) or not isinstance(raw, dict):
        return PriorIdentityState(
            status="absent",
            detail="No preceding observation has been recorded at this path.",
            record=None,
        )
    return _readable(block=cast("dict[str, object]", raw))


def write_identity_state(*, path: Path, record: CodexIdentityStateRecord) -> str | None:
    """Record this observation, returning a detail string if it was not written."""
    text = json.dumps(_encode(record=record), indent=2, sort_keys=True) + "\n"
    written = attempt(action=lambda: _write(path=path, text=text), exceptions=(OSError,))
    if isinstance(written, AttemptFailure):
        return f"This observation was not recorded: {written.error}"
    return None


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _encode(*, record: CodexIdentityStateRecord) -> dict[str, object]:
    return {
        _SCHEMA_FIELD: IDENTITY_STATE_SCHEMA,
        _OBSERVED_AT_FIELD: record.observed_at_epoch,
        _EXPIRES_AT_FIELD: record.expires_at_epoch,
        _TOKEN_FIELD: record.token_fingerprint,
    }


def _readable(*, block: dict[str, object]) -> PriorIdentityState:
    return PriorIdentityState(
        status="readable",
        detail="The preceding observation was read.",
        record=CodexIdentityStateRecord(
            token_fingerprint=_str_field(block=block, name=_TOKEN_FIELD),
            expires_at_epoch=_int_field(block=block, name=_EXPIRES_AT_FIELD),
            observed_at_epoch=_int_field(block=block, name=_OBSERVED_AT_FIELD) or 0,
        ),
    )


def _str_field(*, block: dict[str, object], name: str) -> str | None:
    value = block.get(name)
    if isinstance(value, str) and value != "":
        return value
    return None


def _int_field(*, block: dict[str, object], name: str) -> int | None:
    value = block.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value

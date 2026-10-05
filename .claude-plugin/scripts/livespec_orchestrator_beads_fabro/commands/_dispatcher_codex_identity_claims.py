"""One-way fingerprints of the host Codex access token's identity claims.

The PURE half of the opt-in credential observation. The host access token is a
session-bound JWT whose payload carries a per-token identifier, so observing
that identifier across a natural refresh is what makes a rotation visible
without ever asking the provider for anything.

Nothing here returns a raw claim value. Every identifier leaves this module as
a truncated SHA-256 over a domain-separated string, because the observation is
only ever asked whether two readings are EQUAL -- a question a one-way digest
answers exactly as well as the value does, while being useless to anyone who
reads the persisted file or the operator output.
"""

from __future__ import annotations

import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    decode_codex_access_token_claims,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "TOKEN_CLAIM_NAMES",
    "CodexIdentityClaims",
    "fingerprint_identity_claim",
    "read_codex_identity_claims",
]

# Domain separation, so a digest recorded here cannot be matched against a
# digest of the same value taken anywhere else.
_FINGERPRINT_DOMAIN = "livespec-codex-identity/v1"
# 32 hex characters is 128 bits -- far past any collision that could make two
# genuinely different identifiers read as one unchanged observation.
_FINGERPRINT_HEX_LENGTH = 32

# The per-token identifier, spelled as the observed decode of a live host
# `auth.json` spells it.
TOKEN_CLAIM_NAMES = ("jti",)


@dataclass(frozen=True, kw_only=True)
class CodexIdentityClaims:
    """The fingerprinted identity reading of one host access token.

    `readable` is False when there was no credential to read or its access
    token could not be decoded. It is deliberately separate from a fingerprint
    being None, which means the credential WAS decoded and simply carried no
    such claim -- the two are different facts and the observation reports them
    differently.
    """

    readable: bool
    token_fingerprint: str | None
    expires_at_epoch: int | None


def fingerprint_identity_claim(*, value: str) -> str:
    """Return the one-way fingerprint this observation compares readings by."""
    material = f"{_FINGERPRINT_DOMAIN}:{value}".encode()
    return hashlib.sha256(material).hexdigest()[:_FINGERPRINT_HEX_LENGTH]


def read_codex_identity_claims(*, source_auth_json: str | None) -> CodexIdentityClaims:
    """Fingerprint the identity claims of a host `auth.json`'s access token.

    Never raises: an absent or undecodable credential is an unreadable
    observation rather than a failure, because a status command that died on a
    malformed credential would lose the lifetime reading it exists to print.
    """
    if source_auth_json is None:
        return _unreadable()
    claims = attempt(
        action=lambda: decode_codex_access_token_claims(source_auth_json=source_auth_json),
        exceptions=(ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError),
    )
    if isinstance(claims, AttemptFailure):
        return _unreadable()
    return CodexIdentityClaims(
        readable=True,
        token_fingerprint=_claim_fingerprint(claims=claims, names=TOKEN_CLAIM_NAMES),
        expires_at_epoch=_int_claim(claims=claims, name="exp"),
    )


def _claim_fingerprint(*, claims: dict[str, Any], names: tuple[str, ...]) -> str | None:
    """Fingerprint the first of `names` the claim set carries as a non-empty string."""
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value != "":
            return fingerprint_identity_claim(value=value)
    return None


def _int_claim(*, claims: dict[str, Any], name: str) -> int | None:
    """Return an integer claim, or None when it is absent or not an integer."""
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _unreadable() -> CodexIdentityClaims:
    return CodexIdentityClaims(readable=False, token_fingerprint=None, expires_at_epoch=None)

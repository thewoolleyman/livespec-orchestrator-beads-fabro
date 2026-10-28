"""The ONE bounded request that reads a projected Codex credential's usage windows.

`SPECIFICATION/contracts.md` paragraph "Admission filters Codex candidates by
projected usage-window headroom": for each distinct projected Codex credential
the Dispatcher issues exactly one bounded read to the provider's account usage
endpoint, authenticated by the credential snapshot's access token and account
identifier. The read has a finite timeout and runs no model turn.

THE CREDENTIAL IS THE SNAPSHOT THE DISPATCH WOULD PROJECT: the host `auth.json`
text arrives as a value, and its `tokens.access_token` and `tokens.account_id`
are the only two fields read. An absent or unreadable snapshot issues NO
request: there is nothing to authenticate with, and a request with no
credential could only report the absence the caller already holds.

NOTHING LEAVES THIS MODULE BUT A GRADED READING. The body is read under a byte
bound and decoded here; the only values that escape are the graded reading, an
unobservable REASON from the closed set the Claude read already names, and the
opaque identity. The identity is a domain-separated one-way digest of the
ACCOUNT identifier, not of the access token: the usage window belongs to the
account, and a token rotates on every host refresh, which would otherwise make
every refreshed credential look like a new one and discard its baseline.
"""

from __future__ import annotations

import hashlib
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexHeadroomReading,
    codex_headroom_reading,
    unobservable_codex_headroom,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    ABSENT_CREDENTIAL_IDENTITY,
    ABSENT_CREDENTIAL_REASON,
    AUTHENTICATION_FAILED_REASON,
    TIMED_OUT_REASON,
    TRANSPORT_FAILED_REASON,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "CODEX_HEADROOM_READ_TIMEOUT_SECONDS",
    "CODEX_USAGE_URL",
    "codex_credential_identity",
    "read_projected_codex_headroom",
]

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

# Finite, as the clause requires, and the same bound the Claude read uses.
CODEX_HEADROOM_READ_TIMEOUT_SECONDS = 20.0

_MAX_BODY_BYTES = 1_048_576
_FINGERPRINT_DOMAIN = "livespec-codex-session-headroom-credential"
_FINGERPRINT_HEX_LENGTH = 16
_AUTHENTICATION_STATUSES = frozenset({401, 403})


def codex_credential_identity(*, account_id: str | None) -> str:
    """The opaque, non-secret identity the journal names this credential by."""
    if not account_id:
        return ABSENT_CREDENTIAL_IDENTITY
    material = f"{_FINGERPRINT_DOMAIN}:{account_id}".encode()
    return hashlib.sha256(material).hexdigest()[:_FINGERPRINT_HEX_LENGTH]


def read_projected_codex_headroom(
    *, auth_json: str | None, observed_at: str
) -> CodexHeadroomReading:
    """Read both usage windows for the exact credential snapshot a dispatch projects."""
    token, account_id = _credential_fields(auth_json=auth_json)
    identity = codex_credential_identity(account_id=account_id)
    if not token or not account_id:
        return unobservable_codex_headroom(
            credential_identity=identity,
            observed_at=observed_at,
            reason=ABSENT_CREDENTIAL_REASON,
        )
    body = _usage_body(token=token, account_id=account_id)
    if isinstance(body, str):
        return unobservable_codex_headroom(
            credential_identity=identity, observed_at=observed_at, reason=body
        )
    return codex_headroom_reading(
        credential_identity=identity, observed_at=observed_at, response=_decoded(body=body)
    )


def _credential_fields(*, auth_json: str | None) -> tuple[str | None, str | None]:
    if auth_json is None:
        return (None, None)
    parsed = parse_json(text=auth_json)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return (None, None)
    tokens = cast("dict[str, object]", parsed).get("tokens")
    if not isinstance(tokens, dict):
        return (None, None)
    fields = cast("dict[str, object]", tokens)
    return (_text(value=fields.get("access_token")), _text(value=fields.get("account_id")))


def _text(*, value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _usage_body(*, token: str, account_id: str) -> bytes | str:
    """The response body, or the closed unobservable reason that replaced it."""
    request = Request(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
        CODEX_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "ChatGPT-Account-Id": account_id,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            request, timeout=CODEX_HEADROOM_READ_TIMEOUT_SECONDS
        ) as response:
            return bytes(response.read(_MAX_BODY_BYTES))
    except HTTPError as error:
        if error.code in _AUTHENTICATION_STATUSES:
            return AUTHENTICATION_FAILED_REASON
        return TRANSPORT_FAILED_REASON
    except TimeoutError:
        return TIMED_OUT_REASON
    except (URLError, OSError):
        return TRANSPORT_FAILED_REASON


def _decoded(*, body: bytes) -> object:
    """The decoded JSON body, or `None` when it is not decodable text JSON."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure):
        return None
    return parsed

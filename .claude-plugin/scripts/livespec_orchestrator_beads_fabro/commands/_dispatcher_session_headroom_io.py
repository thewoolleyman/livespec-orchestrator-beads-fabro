"""The ONE bounded request that reads a projected credential's usage window.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": the Dispatcher "MUST read the provider's five-hour
session utilization using the exact credential snapshot that the dispatch would
project", and "The usage request MUST have a finite implementation-defined
timeout."

WHY THIS IS NOT THE EXISTING CREDENTIAL PROBE, which is the question a reader
arrives with. `_dispatcher_claude_credential_io` spends one output token on the
Messages API and answers "is this credential USABLE". That probe reports
`usable` right up to the session limit -- measured on hp 2026-10-14, run
01M4W1W22FZP was refused mid-implement with "You have hit your session limit"
at 03:39Z while `claude-cred-status` still returned condition `usable` / HTTP
200 at 03:41:33Z. Usability and HEADROOM are different measurements of the same
credential, and this clause exists precisely because the first cannot stand in
for the second.

NOTHING LEAVES THIS MODULE BUT A GRADED READING. The response body is read
under a byte bound and decoded here; the only values that escape are a float,
an unobservable REASON from the closed set below, and the opaque identity. So
the "MUST NOT contain credential values or raw provider responses" rule is
discharged at the boundary that holds the raw bytes rather than by every
downstream surface remembering it.

THE IDENTITY IS A ONE-WAY DIGEST, AND THAT IS ENOUGH. Everything the journal
needs the identity for -- telling two readings of one credential apart from
readings of two -- is an EQUALITY question, which a domain-separated digest
answers exactly as well as the credential would, and it cannot be replayed
against the provider. The domain separator is what keeps this fingerprint from
colliding with the Codex identity-continuity fingerprint over the same bytes.

AN ABSENT CREDENTIAL ISSUES NO REQUEST. There is nothing to authenticate with,
so a round trip could only report the absence the caller already holds -- and
an absent credential is the one state where a request would be sent with no
Authorization header at all.
"""

from __future__ import annotations

import hashlib
import json
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
    session_headroom_reading,
    unobservable_session_headroom,
)

__all__: list[str] = [
    "ABSENT_CREDENTIAL_IDENTITY",
    "ABSENT_CREDENTIAL_REASON",
    "AUTHENTICATION_FAILED_REASON",
    "CLAUDE_SESSION_USAGE_URL",
    "SESSION_HEADROOM_READ_TIMEOUT_SECONDS",
    "TIMED_OUT_REASON",
    "TRANSPORT_FAILED_REASON",
    "projected_credential_identity",
    "read_projected_session_headroom",
]

CLAUDE_SESSION_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# Finite, as the clause requires in as many words, and the same bound the
# sibling credential probe uses: both are one bounded request on the admission
# path, and a dispatch waiting on either is a dispatch not launching.
SESSION_HEADROOM_READ_TIMEOUT_SECONDS = 20.0

# The closed set of unobservable reasons THIS module can observe, one per
# measurement that can fail. They are distinct values rather than one generic
# token because their remedies differ: an authentication failure is a rotated
# or revoked credential, a transport failure is the network or the provider,
# and a timeout is neither.
ABSENT_CREDENTIAL_REASON = "absent-credential"
AUTHENTICATION_FAILED_REASON = "authentication-failed"
TIMED_OUT_REASON = "timed-out"
TRANSPORT_FAILED_REASON = "transport-failed"

# The identity reported when there is no credential to fingerprint. A literal
# rather than a digest of the empty string, so a reader is told the credential
# was ABSENT rather than handed a hash of nothing.
ABSENT_CREDENTIAL_IDENTITY = "absent"

_FIVE_HOUR_KEY = "five_hour"
_UTILIZATION_KEY = "utilization"
_FINGERPRINT_DOMAIN = "livespec-session-headroom-credential"
_FINGERPRINT_HEX_LENGTH = 16
_MAX_RESPONSE_BYTES = 65_536
_ANTHROPIC_VERSION = "2023-06-01"
_CLAUDE_OAUTH_BETA = "oauth-2025-04-20"
_AUTHENTICATION_STATUSES = frozenset({401, 403})


def projected_credential_identity(*, token: str | None) -> str:
    """The opaque, non-secret identity the journal names this credential by."""
    if not token:
        return ABSENT_CREDENTIAL_IDENTITY
    material = f"{_FINGERPRINT_DOMAIN}:{token}".encode()
    return hashlib.sha256(material).hexdigest()[:_FINGERPRINT_HEX_LENGTH]


def read_projected_session_headroom(
    *, token: str | None, observed_at: str
) -> SessionHeadroomReading:
    """Read the five-hour window for the exact token a dispatch would project."""
    identity = projected_credential_identity(token=token)
    if not token:
        return unobservable_session_headroom(
            credential_identity=identity,
            observed_at=observed_at,
            reason=ABSENT_CREDENTIAL_REASON,
        )
    payload = _usage_payload(token=token)
    if isinstance(payload, str):
        return unobservable_session_headroom(
            credential_identity=identity, observed_at=observed_at, reason=payload
        )
    return session_headroom_reading(
        credential_identity=identity,
        observed_at=observed_at,
        utilization=_five_hour_utilization(payload=payload),
    )


def _usage_payload(*, token: str) -> dict[str, object] | str:
    """The decoded usage document, or the NAME of the measurement that failed.

    A `str` return is an unobservable reason rather than an error message: the
    caller journals it verbatim, so it must be one of the closed reasons above
    and must never carry the provider's own sentence, which is a raw provider
    response.
    """
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            _usage_request(token=token),
            timeout=SESSION_HEADROOM_READ_TIMEOUT_SECONDS,
        ) as response:
            body = response.read(_MAX_RESPONSE_BYTES)
    except HTTPError as error:
        return _http_reason(status=error.code)
    except TimeoutError:
        return TIMED_OUT_REASON
    except (URLError, OSError):
        return TRANSPORT_FAILED_REASON
    return _json_object(body=body)


def _usage_request(*, token: str) -> Request:
    return Request(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
        CLAUDE_SESSION_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": _CLAUDE_OAUTH_BETA,
            "anthropic-version": _ANTHROPIC_VERSION,
        },
        method="GET",
    )


def _http_reason(*, status: int) -> str:
    """Which unobservable reason one refused status code reports."""
    if status in _AUTHENTICATION_STATUSES:
        return AUTHENTICATION_FAILED_REASON
    return TRANSPORT_FAILED_REASON


def _five_hour_utilization(*, payload: dict[str, object]) -> object:
    """The five-hour window's utilization figure as the document carries it.

    Returned UNGRADED, as an `object`, because grading it is the reading's own
    job: a shape this function rejected would have to be reported as some
    sentinel, and every sentinel available is also a valid utilization.
    """
    window = payload.get(_FIVE_HOUR_KEY)
    if not isinstance(window, dict):
        return None
    return cast("dict[str, object]", window).get(_UTILIZATION_KEY)


def _json_object(*, body: bytes) -> dict[str, object]:
    """The body as a JSON object, or the empty object for anything else."""
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast("dict[str, object]", parsed)

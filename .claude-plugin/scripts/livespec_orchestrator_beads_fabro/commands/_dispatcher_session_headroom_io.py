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

WHY THE READING RIDES A MESSAGES REQUEST AND NOT THE OAUTH USAGE ENDPOINT
(`bd-ib-nzp5ln`). The first build of this module read `GET /api/oauth/usage`.
That endpoint requires the `user:profile` OAuth scope, which the projected
inference-scoped subscription token does not hold: measured on this host
2026-10-15 it answered 403 `permission_error` ("OAuth token does not meet scope
requirement user:profile") and then 429 on every retry, so EVERY admission
evaluation graded the reading unobservable and skipped every covered
candidate. The same token on a one-output-token `POST /v1/messages` answered
200 with `anthropic-ratelimit-unified-5h-utilization: 0.0`, so the five-hour
window IS observable for this credential, from that response header. The
header is a FRACTION of the allowance; it is multiplied by 100 here so the
shared grader sees the percentage the clause measures. A refused response that
still carries the header -- a 429 at the session limit does -- is graded from
the header, because it answers the question exactly as a 200 would.

THE SAME RESPONSE ANSWERS THE SEVEN-DAY WINDOW, AND IT IS READ HERE RATHER
THAN IN A SECOND REQUEST (`bd-ib-rszkjc`). Measured on this host 2026-10-15,
the factory token answered `anthropic-ratelimit-unified-7d-utilization: 0.95`
with a 7d status of `allowed_warning` while the five-hour window was barely
touched, so the next cliff was the seven-day one and the five-hour floor cannot
see it. Both headers are fractions and both are multiplied by 100 here.

The two windows are graded INDEPENDENTLY from the one response, which is the
property an almost-correct implementation collapses: a refusal carrying no
five-hour header is unobservable FOR THAT WINDOW, and the seven-day header it
did carry is still an answer. Dropping it there would report an absence the
response contradicts. The seven-day figure is journal-only, so no failure to
read it can refuse a dispatch.

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
from dataclasses import dataclass
from email.message import Message
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
    "CLAUDE_SESSION_HEADROOM_MAX_OUTPUT_TOKENS",
    "CLAUDE_SESSION_HEADROOM_MODEL",
    "CLAUDE_SESSION_HEADROOM_URL",
    "FIVE_HOUR_UTILIZATION_HEADER",
    "SESSION_HEADROOM_READ_TIMEOUT_SECONDS",
    "SEVEN_DAY_UTILIZATION_HEADER",
    "TIMED_OUT_REASON",
    "TRANSPORT_FAILED_REASON",
    "projected_credential_identity",
    "read_projected_session_headroom",
]

CLAUDE_SESSION_HEADROOM_URL = "https://api.anthropic.com/v1/messages"

# The cheapest request the Messages API answers, and the same one the sibling
# credential probe spends: one output token on the smallest current model.
CLAUDE_SESSION_HEADROOM_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_SESSION_HEADROOM_MAX_OUTPUT_TOKENS = 1
FIVE_HOUR_UTILIZATION_HEADER = "anthropic-ratelimit-unified-5h-utilization"
SEVEN_DAY_UTILIZATION_HEADER = "anthropic-ratelimit-unified-7d-utilization"

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

_PERCENT_PER_FRACTION = 100.0
_FINGERPRINT_DOMAIN = "livespec-session-headroom-credential"
_FINGERPRINT_HEX_LENGTH = 16
_ANTHROPIC_VERSION = "2023-06-01"
_CLAUDE_OAUTH_BETA = "oauth-2025-04-20"
_AUTHENTICATION_STATUSES = frozenset({401, 403})


@dataclass(frozen=True, kw_only=True)
class _UsageWindows:
    """Both windows ONE response reported, or the failure that stopped the read.

    The two windows are separate fields rather than one value because they are
    separate answers: a response can carry either, both or neither, and a
    `failure` naming the measurement that stopped the FIVE-HOUR read says
    nothing about a seven-day header that arrived on the same response.
    """

    five_hour: float | None = None
    seven_day: float | None = None
    failure: str | None = None


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
    windows = _usage_windows(token=token)
    if windows.failure is not None:
        return unobservable_session_headroom(
            credential_identity=identity,
            observed_at=observed_at,
            reason=windows.failure,
            seven_day_utilization_percent=windows.seven_day,
        )
    return session_headroom_reading(
        credential_identity=identity,
        observed_at=observed_at,
        utilization=windows.five_hour,
        seven_day_utilization_percent=windows.seven_day,
    )


def _usage_windows(*, token: str) -> _UsageWindows:
    """Both windows one bounded request reported, or the failure that stopped it.

    A `failure` is an unobservable reason rather than an error message: the
    caller journals it verbatim, so it must be one of the closed reasons above
    and must never carry the provider's own sentence, which is a raw provider
    response. A response with no parseable five-hour header carries NO failure
    -- the provider answered -- and the shared grader reports that as an
    unreadable utilization.
    """
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            _headroom_request(token=token),
            timeout=SESSION_HEADROOM_READ_TIMEOUT_SECONDS,
        ) as response:
            return _response_windows(headers=response.headers)
    except HTTPError as error:
        windows = _response_windows(headers=error.headers)
        if windows.five_hour is not None:
            return windows
        return _UsageWindows(seven_day=windows.seven_day, failure=_http_reason(status=error.code))
    except TimeoutError:
        return _UsageWindows(failure=TIMED_OUT_REASON)
    except (URLError, OSError):
        return _UsageWindows(failure=TRANSPORT_FAILED_REASON)


def _response_windows(*, headers: Message | None) -> _UsageWindows:
    """One response's two utilization headers, each graded on its own."""
    return _UsageWindows(
        five_hour=_header_percent(headers=headers, name=FIVE_HOUR_UTILIZATION_HEADER),
        seven_day=_header_percent(headers=headers, name=SEVEN_DAY_UTILIZATION_HEADER),
    )


def _headroom_request(*, token: str) -> Request:
    body = json.dumps(
        {
            "model": CLAUDE_SESSION_HEADROOM_MODEL,
            "max_tokens": CLAUDE_SESSION_HEADROOM_MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": "hi"}],
        },
        separators=(",", ":"),
    ).encode()
    return Request(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
        CLAUDE_SESSION_HEADROOM_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": _CLAUDE_OAUTH_BETA,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )


def _http_reason(*, status: int) -> str:
    """Which unobservable reason one refused status code reports."""
    if status in _AUTHENTICATION_STATUSES:
        return AUTHENTICATION_FAILED_REASON
    return TRANSPORT_FAILED_REASON


def _header_percent(*, headers: Message | None, name: str) -> float | None:
    """One named utilization header as a percentage, or `None` when unreadable.

    Range and finiteness are NOT checked here: grading is the reading's own
    job, and a value this function silently clamped would be a coerced reading.
    The header NAME is a parameter rather than a constant because both windows
    are the same fraction-of-allowance encoding, and a second copy of this
    function is how one window comes to be multiplied by 100 and the other not.
    """
    if headers is None:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw) * _PERCENT_PER_FRACTION
    except ValueError:
        return None

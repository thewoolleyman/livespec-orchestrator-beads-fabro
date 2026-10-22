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

BOTH WINDOWS COME OFF ONE RESPONSE, which is the seven-day clause's own
wording -- "From the same provider response it MUST also take the seven-day
utilization and the seven-day status" -- and the reason this module reads four
headers rather than issuing a second request. The admission path spends one
bounded request per credential per evaluation, so a second round trip for the
weekly half would double what the brake costs the provider while answering a
question the first response already answered.

THE SEVEN-DAY HEADER NAMES ARE THE MEASURED FIVE-HOUR HEADER'S SIBLINGS, not a
second measurement. `anthropic-ratelimit-unified-5h-utilization` was measured
on this host (see below); the weekly pair is the same unified rate-limit
family's `7d` spelling. That is stated rather than implied because the
consequence of being wrong matters: an unrecognised header reads as an ABSENT
weekly reading, which the clause forbids from skipping anything, so a wrong
spelling degrades to the five-hour-only behaviour this module already had
rather than to a wrong refusal. The DECISION is also immune to whether the
weekly figure is a fraction or a percentage -- the status decides, and the
figure is only journaled -- so the conversion below can be wrong without any
candidate being skipped or admitted differently.

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
from dataclasses import dataclass, replace
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    UNOBSERVABLE_SEVEN_DAY,
    SessionHeadroomReading,
    SevenDayReading,
    session_headroom_reading,
    seven_day_reading,
    unobservable_session_headroom,
)

__all__: list[str] = [
    "ABSENT_CREDENTIAL_IDENTITY",
    "ABSENT_CREDENTIAL_REASON",
    "AUTHENTICATION_FAILED_REASON",
    "CLAUDE_SESSION_HEADROOM_MAX_OUTPUT_TOKENS",
    "CLAUDE_SESSION_HEADROOM_MODEL",
    "CLAUDE_SESSION_HEADROOM_URL",
    "FIVE_HOUR_RESET_HEADER",
    "FIVE_HOUR_UTILIZATION_HEADER",
    "SESSION_HEADROOM_READ_TIMEOUT_SECONDS",
    "SEVEN_DAY_STATUS_HEADER",
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

# The provider's own claim about when the five-hour window resets. It is read
# and carried, never acted on: the clause permits journaling it as "an
# unverified provider claim" and forbids it from changing the projection skip,
# and nothing here or downstream has a second source to check it against.
FIVE_HOUR_RESET_HEADER = "anthropic-ratelimit-unified-5h-reset"

# The seven-day window, which the same response reports beside the five-hour
# one. The STATUS is the field the clause's skip turns on; the utilization is
# journaled and grades nothing, which is why it carries the same
# fraction-to-percentage conversion as its five-hour sibling without that
# conversion being able to change any decision.
SEVEN_DAY_UTILIZATION_HEADER = "anthropic-ratelimit-unified-7d-utilization"
SEVEN_DAY_STATUS_HEADER = "anthropic-ratelimit-unified-7d-status"

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
class _ProviderWindows:
    """What ONE request came back with: both windows, or the fault instead.

    A value rather than a widening tuple, which is what the five-hour-only read
    carried. Two windows plus a reset claim plus a fault name is four slots
    whose meanings are not interchangeable, and a positional reader of four is
    exactly how a response's weekly status comes to be read as its reset claim.

    `reason` being set is what makes this a FAULT: the two windows are then
    whatever could still be read off a refused response, which the caller
    journals beside the unobservable five-hour result.
    """

    utilization: float | None = None
    reason: str | None = None
    reset_claim: str | None = None
    seven_day: SevenDayReading = UNOBSERVABLE_SEVEN_DAY


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
    windows = _provider_windows(token=token)
    if windows.reason is not None:
        return unobservable_session_headroom(
            credential_identity=identity,
            observed_at=observed_at,
            reason=windows.reason,
            provider_reset_claim=windows.reset_claim,
            seven_day=windows.seven_day,
        )
    return session_headroom_reading(
        credential_identity=identity,
        observed_at=observed_at,
        utilization=windows.utilization,
        provider_reset_claim=windows.reset_claim,
        seven_day=windows.seven_day,
    )


def _provider_windows(*, token: str) -> _ProviderWindows:
    """Both usage windows off ONE bounded request, or the fault that replaced them.

    The fault name is one of the closed reasons above and never the provider's
    own sentence, which is a raw provider response and may not be journaled.

    EVERY ANSWER THE PROVIDER ACTUALLY GAVE IS READ, including a refused one --
    a 429 at a session or weekly limit is exactly the response most likely to
    carry the figures -- and the two faults where no response exists carry
    nothing, because there is nothing to read them off.
    """
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            _headroom_request(token=token),
            timeout=SESSION_HEADROOM_READ_TIMEOUT_SECONDS,
        ) as response:
            return _answered(headers=response.headers)
    except HTTPError as error:
        answered = _answered(headers=error.headers)
        if answered.utilization is not None:
            return answered
        return replace(answered, reason=_http_reason(status=error.code))
    except TimeoutError:
        return _ProviderWindows(reason=TIMED_OUT_REASON)
    except (URLError, OSError):
        return _ProviderWindows(reason=TRANSPORT_FAILED_REASON)


def _answered(*, headers: Message | None) -> _ProviderWindows:
    """Every window one ANSWERED response reports, graded.

    Shared by the success and refusal arms rather than written twice, which is
    what keeps a refused response from being read differently than a 200 -- the
    whole reason the five-hour header is taken off a 429 at all.
    """
    return _ProviderWindows(
        utilization=_header_percent(headers=headers, name=FIVE_HOUR_UTILIZATION_HEADER),
        reset_claim=_header_text(headers=headers, name=FIVE_HOUR_RESET_HEADER),
        seven_day=seven_day_reading(
            utilization=_header_percent(headers=headers, name=SEVEN_DAY_UTILIZATION_HEADER),
            status=_header_text(headers=headers, name=SEVEN_DAY_STATUS_HEADER),
        ),
    )


def _header_text(*, headers: Message | None, name: str) -> str | None:
    """One header's own text, verbatim, or `None` when it is not there.

    No parsing and no validation. Of its two callers, the reset claim is read
    by no decision at all -- so a parse would be work performed to produce a
    value nothing consumes, and a parse that FAILED would discard the claim the
    clause permits journaling -- and the seven-day status is graded by the
    shared reading, which owns what counts as exhaustion.
    """
    if headers is None:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    return str(raw)


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
    """One utilization header as a percentage, or `None` when it cannot be read.

    Range and finiteness are NOT checked here: grading is the reading's own
    job, and a value this function silently clamped would be a coerced reading.

    The header is named by the CALLER because both windows report their
    utilization the same way, and one function reading a fixed name is how the
    weekly figure comes to be reported as the five-hour one.
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

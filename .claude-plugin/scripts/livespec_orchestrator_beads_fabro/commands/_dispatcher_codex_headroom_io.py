"""The ONE bounded request that reads a projected Codex credential's usage.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "For each distinct projected Codex credential per admission
evaluation, the Dispatcher MUST issue exactly one bounded usage read to the
provider's account usage endpoint, `https://chatgpt.com/backend-api/wham/usage`,
authenticated by that snapshot's access token and account identifier, and MUST
reuse that one reading across every node and candidate sharing the credential.
The read MUST have a finite implementation-defined timeout and MUST NOT run a
model turn or spend any model allowance."

WHY THIS IS NOT THE EXISTING CODEX CREDENTIAL GATE, which is the question a
reader arrives with. `_dispatcher_codex_credential_gate` asks whether the
projected credential's access token OUTLIVES the run budget, and renews it in
place when it does not. That is a question about the credential's LIFETIME, and
a credential with twelve hours of lifetime and no usage allowance left passes it
and is then refused by the provider mid-turn. This clause exists because the
first measurement cannot stand in for the second.

IT SPENDS NO MODEL ALLOWANCE, WHICH IS A PROPERTY OF THE ENDPOINT RATHER THAN OF
THIS CODE. The ratified endpoint is an account USAGE read -- a `GET` with no
body -- so there is no prompt, no model and no turn, and the clause's "MUST NOT
run a model turn or spend any model allowance" holds structurally. That is the
one way it differs in kind from the Claude read beside it, which has no usage
endpoint available to the projected token and must ride a one-output-token
Messages request.

NOTHING LEAVES THIS MODULE BUT A GRADED READING. The response body is read under
a byte bound and decoded here; the only values that escape are the graded
reading and the opaque identity. So "The journal MUST NOT contain credential
values, the account email, or raw provider responses" is discharged at the
boundary that HOLDS the raw bytes rather than by every downstream surface
remembering it -- and the account email, which this endpoint's payload does
carry, never reaches a value the record can render.

THE IDENTITY IS A ONE-WAY DIGEST, AND THAT IS ENOUGH. Everything the journal
needs it for -- telling two readings of one credential apart from readings of
two -- is an EQUALITY question, which a domain-separated digest answers exactly
as well as the token would, and it cannot be replayed against the provider. The
domain separator is what keeps this fingerprint from colliding with the Claude
headroom fingerprint or the Codex identity-continuity fingerprint over the same
bytes.

AN UNUSABLE SNAPSHOT ISSUES NO REQUEST. A snapshot with no access token or no
account identifier cannot authenticate one, so a round trip could only report
the absence the caller already holds -- and it is the one state where a request
would be sent with no `Authorization` header at all. The two faults are reported
as ONE reason, because the remedy is identical: the host credential needs a
`codex login`.
"""

from __future__ import annotations

import hashlib
import json
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CodexUsageReading,
    codex_usage_reading,
    unobservable_codex_usage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    ABSENT_CREDENTIAL_IDENTITY,
    ABSENT_CREDENTIAL_REASON,
    AUTHENTICATION_FAILED_REASON,
    TIMED_OUT_REASON,
    TRANSPORT_FAILED_REASON,
)

__all__: list[str] = [
    "ABSENT_CREDENTIAL_IDENTITY",
    "ABSENT_CREDENTIAL_REASON",
    "AUTHENTICATION_FAILED_REASON",
    "CODEX_ACCOUNT_HEADER",
    "CODEX_USAGE_READ_TIMEOUT_SECONDS",
    "CODEX_USAGE_URL",
    "RATE_LIMIT_FIELD",
    "TIMED_OUT_REASON",
    "TRANSPORT_FAILED_REASON",
    "UNREADABLE_RESPONSE_REASON",
    "projected_codex_credential_identity",
    "read_projected_codex_usage",
]

# The ratified endpoint, spelled exactly as the clause spells it.
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

# The header the provider identifies the account by, which the clause requires
# the read to be authenticated by alongside the access token: one login can
# carry several accounts, so a token alone names no usage window.
CODEX_ACCOUNT_HEADER = "chatgpt-account-id"

# Finite, as the clause requires in as many words, and the same bound the
# Claude read uses: both are one bounded request on the admission path, and a
# dispatch waiting on either is a dispatch not launching.
CODEX_USAGE_READ_TIMEOUT_SECONDS = 20.0

# The block every graded field is read out of. Named because the clause's "A
# credit balance, an overage allowance, or any other field outside `rate_limit`
# MUST NOT count as headroom" is enforced by reading ONLY this key.
RATE_LIMIT_FIELD = "rate_limit"

# The one unobservable reason THIS module adds to the four it shares with its
# Claude sibling: a response that answered but did not decode into an object.
# The four shared reasons are imported rather than respelled, because their
# remedies are identical for both providers and two vocabularies for one set of
# faults is how a reader comes to think they are different faults.
UNREADABLE_RESPONSE_REASON = "unreadable-response"

_FINGERPRINT_DOMAIN = "livespec-codex-usage-credential"
_FINGERPRINT_HEX_LENGTH = 16
_AUTHENTICATION_STATUSES = frozenset({401, 403})
# A usage payload is a few hundred bytes. The bound exists so a provider
# answering with something enormous cannot be read into this process at all.
_MAX_RESPONSE_BYTES = 262144


def projected_codex_credential_identity(*, access_token: str | None) -> str:
    """The opaque, non-secret identity the journal names this credential by."""
    if not access_token:
        return ABSENT_CREDENTIAL_IDENTITY
    material = f"{_FINGERPRINT_DOMAIN}:{access_token}".encode()
    return hashlib.sha256(material).hexdigest()[:_FINGERPRINT_HEX_LENGTH]


def read_projected_codex_usage(*, auth_json: str | None, observed_at: str) -> CodexUsageReading:
    """Read the usage window for the exact snapshot a dispatch would project.

    `auth_json` is the `auth.json` TEXT rather than a path, so this module
    performs no host-file read of its own: the snapshot is resolved by the
    caller that already owns that read, which is what keeps one dispatch's
    credential from being read twice and graded differently.
    """
    snapshot = _snapshot(auth_json=auth_json)
    if snapshot is None:
        return unobservable_codex_usage(
            credential_identity=ABSENT_CREDENTIAL_IDENTITY,
            observed_at=observed_at,
            reason=ABSENT_CREDENTIAL_REASON,
        )
    access_token, account_id = snapshot
    identity = projected_codex_credential_identity(access_token=access_token)
    answered = _usage_payload(access_token=access_token, account_id=account_id)
    if isinstance(answered, str):
        return unobservable_codex_usage(
            credential_identity=identity, observed_at=observed_at, reason=answered
        )
    return codex_usage_reading(
        credential_identity=identity,
        observed_at=observed_at,
        rate_limit=answered.get(RATE_LIMIT_FIELD),
    )


def _snapshot(*, auth_json: str | None) -> tuple[str, str] | None:
    """The access token and account identifier, or `None` for an unusable snapshot.

    Every shape that cannot authenticate a request answers `None`: absent text,
    text that is not JSON, no `tokens` object, and either field missing or
    empty. One answer for all of them, because the remedy is one `codex login`
    and a reader told which field was missing could do nothing different.
    """
    fields = _tokens(auth_json=auth_json)
    if fields is None:
        return None
    access_token = fields.get("access_token")
    account_id = fields.get("account_id")
    if not isinstance(access_token, str) or not isinstance(account_id, str):
        return None
    return (access_token, account_id) if access_token and account_id else None


def _tokens(*, auth_json: str | None) -> dict[str, object] | None:
    """The snapshot's `tokens` object, or `None` when the text does not hold one.

    Split from the grading above so each half reads one question: whether the
    text decodes into a snapshot at all, and whether that snapshot names the
    two values a request needs.
    """
    if not auth_json:
        return None
    try:
        decoded: object = json.loads(auth_json)
    except ValueError:
        return None
    if not isinstance(decoded, dict):
        return None
    tokens = cast("dict[str, object]", decoded).get("tokens")
    return cast("dict[str, object]", tokens) if isinstance(tokens, dict) else None


def _usage_payload(*, access_token: str, account_id: str) -> dict[str, object] | str:
    """The decoded payload off ONE bounded request, or the fault that replaced it.

    The fault name is one of the closed reasons above and never the provider's
    own sentence, which is a raw provider response and may not be journaled.

    A REFUSED response is NOT read for a payload, which is the one place this
    differs from the Claude read beside it: that read takes its figure off a
    rate-limit HEADER a 429 still carries, while this clause's figures live in a
    response BODY that a refusal does not carry at all. So an authentication
    failure and a 429 alike are reported as faults rather than mined for a
    partial reading -- which the clause requires anyway, since a reading missing
    either boolean is unobservable.
    """
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
            _usage_request(access_token=access_token, account_id=account_id),
            timeout=CODEX_USAGE_READ_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read(_MAX_RESPONSE_BYTES)
    except HTTPError as error:
        return (
            AUTHENTICATION_FAILED_REASON
            if error.code in _AUTHENTICATION_STATUSES
            else TRANSPORT_FAILED_REASON
        )
    except TimeoutError:
        return TIMED_OUT_REASON
    except (URLError, OSError):
        return TRANSPORT_FAILED_REASON
    return _decoded(raw=raw)


def _decoded(*, raw: bytes) -> dict[str, object] | str:
    """One response body as an object, or the reason it could not be read as one."""
    try:
        payload: object = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return UNREADABLE_RESPONSE_REASON
    if not isinstance(payload, dict):
        return UNREADABLE_RESPONSE_REASON
    return cast("dict[str, object]", payload)


def _usage_request(*, access_token: str, account_id: str) -> Request:
    """The one `GET` this clause issues, carrying no body and no prompt."""
    return Request(  # noqa: S310 - fixed HTTPS endpoint, no caller-controlled URL.
        CODEX_USAGE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            CODEX_ACCOUNT_HEADER: account_id,
            "accept": "application/json",
        },
        method="GET",
    )

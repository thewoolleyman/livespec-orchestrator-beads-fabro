"""Pure Claude OAuth credential usability assessment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__: list[str] = [
    "CLAUDE_OAUTH_TOKEN_ENV",
    "ClaudeCredentialStatus",
    "ClaudeProbeObservation",
    "absent_claude_credential_status",
    "classify_claude_probe",
]

CLAUDE_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # noqa: S105 - env-var NAME
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_HTTP_PAYMENT_REQUIRED = 402
_HTTP_FORBIDDEN = 403
_HTTP_TOO_MANY_REQUESTS = 429
_CAPACITY_HTTP_STATUSES = frozenset({_HTTP_PAYMENT_REQUIRED, _HTTP_TOO_MANY_REQUESTS})
_ClaudeCredentialCondition = Literal[
    "absent",
    "usable",
    "revoked",
    "exhausted",
    "permission-denied",
    "unavailable",
]


@dataclass(frozen=True, kw_only=True)
class ClaudeProbeObservation:
    """Non-secret result of one bounded Messages API probe."""

    http_status: int | None
    error_type: str | None
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, kw_only=True)
class ClaudeCredentialStatus:
    """Operator-facing assessment of ``CLAUDE_CODE_OAUTH_TOKEN``."""

    condition: _ClaudeCredentialCondition
    present: bool
    usable: bool
    http_status: int | None
    error_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    message: str
    remedy: str


def classify_claude_probe(*, observation: ClaudeProbeObservation) -> ClaudeCredentialStatus:
    """Classify one bounded probe without retaining its response body."""
    if observation.http_status == _HTTP_OK:
        return _status(
            observation=observation,
            condition="usable",
            usable=True,
            message=(
                f"{CLAUDE_OAUTH_TOKEN_ENV} is usable; the bounded Messages API "
                "probe returned HTTP 200."
            ),
            remedy="No action required.",
        )
    if (
        observation.http_status == _HTTP_UNAUTHORIZED
        or observation.error_type == "authentication_error"
    ):
        return _status(
            observation=observation,
            condition="revoked",
            usable=False,
            message=(
                f"{CLAUDE_OAUTH_TOKEN_ENV} is revoked, expired, or malformed "
                "(authentication failed)."
            ),
            remedy=(
                "Run `claude setup-token` under an account with capacity, then "
                "rotate CLAUDE_CODE_OAUTH_TOKEN in the credential wrapper."
            ),
        )
    if observation.http_status in _CAPACITY_HTTP_STATUSES or observation.error_type in {
        "billing_error",
        "rate_limit_error",
    }:
        return _status(
            observation=observation,
            condition="exhausted",
            usable=False,
            message=(
                f"{CLAUDE_OAUTH_TOKEN_ENV} is exhausted or rate-limited "
                f"({_observation_label(observation=observation)})."
            ),
            remedy=(
                "Do not wait until a provider-stated reset instant: a provider's "
                "timing claim is an unverified provider claim, never an instruction, "
                "and no clock gates the retry. The loop re-probes this credential on "
                "dispatcher.credential_reprobe_interval_seconds and resumes admission "
                "on the first usable result. For an org spend or billing limit, raise "
                "the billing limit or re-mint with `claude setup-token` under a "
                "healthy org and rotate the wrapper secret."
            ),
        )
    if observation.http_status == _HTTP_FORBIDDEN or observation.error_type == "permission_error":
        return _status(
            observation=observation,
            condition="permission-denied",
            usable=False,
            message=(
                f"{CLAUDE_OAUTH_TOKEN_ENV} lacks access to the Messages API "
                f"({_observation_label(observation=observation)})."
            ),
            remedy=(
                "Check the token's organization and workspace access, then re-mint "
                "and rotate it if that access cannot be restored."
            ),
        )
    return _status(
        observation=observation,
        condition="unavailable",
        usable=False,
        message=(
            f"{CLAUDE_OAUTH_TOKEN_ENV} usability could not be established "
            f"({_observation_label(observation=observation)})."
        ),
        remedy=(
            "Do not launch the sandbox; retry the bounded credential probe after "
            "checking Anthropic service and network availability."
        ),
    )


def absent_claude_credential_status(*, wrapper_text: str) -> ClaudeCredentialStatus:
    """Return the distinct absent-credential refusal."""
    return ClaudeCredentialStatus(
        condition="absent",
        present=False,
        usable=False,
        http_status=None,
        error_type=None,
        input_tokens=None,
        output_tokens=None,
        message=(
            f"{CLAUDE_OAUTH_TOKEN_ENV} is absent from the Dispatcher's process "
            "environment, so no review credential can be projected."
        ),
        remedy=(
            f"Invoke the Dispatcher under the target credential wrapper {wrapper_text}; "
            f"it must inject {CLAUDE_OAUTH_TOKEN_ENV}."
        ),
    )


def _status(
    *,
    observation: ClaudeProbeObservation,
    condition: _ClaudeCredentialCondition,
    usable: bool,
    message: str,
    remedy: str,
) -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition=condition,
        present=True,
        usable=usable,
        http_status=observation.http_status,
        error_type=observation.error_type,
        input_tokens=observation.input_tokens,
        output_tokens=observation.output_tokens,
        message=message,
        remedy=remedy,
    )


def _observation_label(*, observation: ClaudeProbeObservation) -> str:
    if observation.http_status is None:
        return "probe transport failed before an HTTP response"
    if observation.error_type is None:
        return f"HTTP {observation.http_status}"
    return f"HTTP {observation.http_status}, {observation.error_type}"

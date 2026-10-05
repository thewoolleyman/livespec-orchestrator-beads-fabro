"""Comparing one Codex identity reading with the preceding one.

The pure comparison layer: it takes the current fingerprinted reading and the
remembered one and says, PER IDENTIFIER, whether this is the first observation,
whether the identifier held or moved, or whether it could not be compared at
all.

`unknown` is a first-class verdict rather than a fallback into `unchanged`, and
that choice is the whole point of this layer. A reading with nothing to compare
-- a claim the credential does not carry, a credential that could not be decoded
-- is INDISTINGUISHABLE at the surface from an identifier that genuinely held,
and the two support opposite conclusions. Reporting the absence as stability
would manufacture evidence of continuity out of a failure to observe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_claims import (
    CodexIdentityClaims,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_state import (
    PriorIdentityState,
)

__all__: list[str] = [
    "IDENTITY_CONTINUITY_LIMITATION",
    "CodexIdentityComparison",
    "IdentityChange",
    "IdentityStateWrite",
    "compare_codex_identity",
    "identity_observation_human_lines",
    "identity_observation_payload",
]

IdentityChange = Literal["first-observation", "unchanged", "changed", "unknown"]

# Carried on EVERY observation, machine-readable and human alike, rather than
# left to a runbook. The reading measures identifier continuity; the inference
# an operator reaches for -- "the session held, so the token I already handed a
# worker is still good" -- is a claim about what the provider will accept, and
# nothing observable in the credential file can settle it. Stating the limit
# beside the verdict is the only place it is guaranteed to be read.
IDENTITY_CONTINUITY_LIMITATION = (
    "This observation compares identifiers across readings and nothing more. It "
    "does not establish whether a previously issued access token remains valid: "
    "an unchanged session identifier is no evidence that an older token is still "
    "accepted, and a changed one is no evidence that it was revoked. Only the "
    "provider can answer that."
)


# Three NAMED outcomes rather than a boolean. "Was it written?" cannot express
# the difference between a write this reading deliberately declined and a write
# that failed, and those two want opposite responses from an operator: the first
# is the mechanism protecting the series, the second is a broken state path.
IdentityStateWriteOutcome = Literal["recorded", "withheld", "failed"]


@dataclass(frozen=True, kw_only=True)
class IdentityStateWrite:
    """What became of this reading's attempt to record itself."""

    outcome: IdentityStateWriteOutcome
    detail: str | None


@dataclass(frozen=True, kw_only=True)
class CodexIdentityComparison:
    """What this reading established against the preceding one."""

    prior_state: str
    prior_state_detail: str
    session_change: IdentityChange
    token_change: IdentityChange


def compare_codex_identity(
    *,
    claims: CodexIdentityClaims,
    prior: PriorIdentityState,
) -> CodexIdentityComparison:
    """Compare the current identity reading with the remembered one."""
    record = prior.record
    # Keyed on the PRIOR FILE's existence, not on whether a record parsed out of
    # it. A damaged file means a preceding reading happened and this one cannot
    # see it, which is `unknown` -- reporting `first-observation` there would
    # restart the series over a record still on disk.
    prior_exists = prior.status != "absent"
    return CodexIdentityComparison(
        prior_state=prior.status,
        prior_state_detail=prior.detail,
        session_change=_change(
            current=claims.session_fingerprint,
            prior_value=None if record is None else record.session_fingerprint,
            prior_exists=prior_exists,
        ),
        token_change=_change(
            current=claims.token_fingerprint,
            prior_value=None if record is None else record.token_fingerprint,
            prior_exists=prior_exists,
        ),
    )


def identity_observation_payload(
    *,
    claims: CodexIdentityClaims,
    comparison: CodexIdentityComparison,
    state_path: str,
    write: IdentityStateWrite,
) -> dict[str, Any]:
    """Render the machine-readable observation an operator opted in to."""
    return {
        "claims_readable": claims.readable,
        "expires_at_epoch": claims.expires_at_epoch,
        "limitation": IDENTITY_CONTINUITY_LIMITATION,
        "prior_state": comparison.prior_state,
        "prior_state_detail": comparison.prior_state_detail,
        "session_change": comparison.session_change,
        "session_fingerprint": claims.session_fingerprint,
        "state_path": state_path,
        "state_write": write.outcome,
        "state_write_detail": write.detail,
        "token_change": comparison.token_change,
        "token_fingerprint": claims.token_fingerprint,
    }


def identity_observation_human_lines(*, observation: dict[str, Any] | None) -> tuple[str, ...]:
    """Render the observation as operator-facing lines, or nothing without one."""
    if observation is None:
        return ()
    return (
        f"identity_prior_state: {observation['prior_state']}",
        f"identity_session_change: {observation['session_change']}",
        f"identity_token_change: {observation['token_change']}",
        f"identity_state_path: {observation['state_path']}",
        f"identity_state_write: {observation['state_write']}",
        f"identity_limitation: {observation['limitation']}",
    )


def _change(
    *,
    current: str | None,
    prior_value: str | None,
    prior_exists: bool,
) -> IdentityChange:
    if not prior_exists:
        return "first-observation"
    if current is None or prior_value is None:
        return "unknown"
    return "unchanged" if current == prior_value else "changed"

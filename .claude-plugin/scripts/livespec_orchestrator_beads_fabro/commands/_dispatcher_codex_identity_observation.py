"""Comparing one Codex identity reading with the preceding one.

The pure comparison layer: it takes the current fingerprinted reading and the
remembered one and says, per identifier, whether this is the first observation
or the identifier held or moved.
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
    "CodexIdentityComparison",
    "IdentityChange",
    "compare_codex_identity",
    "identity_observation_human_lines",
    "identity_observation_payload",
]

IdentityChange = Literal["first-observation", "unchanged", "changed"]


@dataclass(frozen=True, kw_only=True)
class CodexIdentityComparison:
    """What this reading established against the preceding one."""

    prior_state: str
    prior_state_detail: str
    token_change: IdentityChange


def compare_codex_identity(
    *,
    claims: CodexIdentityClaims,
    prior: PriorIdentityState,
) -> CodexIdentityComparison:
    """Compare the current identity reading with the remembered one."""
    record = prior.record
    return CodexIdentityComparison(
        prior_state=prior.status,
        prior_state_detail=prior.detail,
        token_change=_change(
            current=claims.token_fingerprint,
            prior_value=None if record is None else record.token_fingerprint,
            prior_present=record is not None,
        ),
    )


def identity_observation_payload(
    *,
    claims: CodexIdentityClaims,
    comparison: CodexIdentityComparison,
    state_path: str,
    state_write_detail: str | None,
) -> dict[str, Any]:
    """Render the machine-readable observation an operator opted in to."""
    return {
        "claims_readable": claims.readable,
        "expires_at_epoch": claims.expires_at_epoch,
        "prior_state": comparison.prior_state,
        "prior_state_detail": comparison.prior_state_detail,
        "state_path": state_path,
        "state_write_detail": state_write_detail,
        "state_written": state_write_detail is None,
        "token_change": comparison.token_change,
        "token_fingerprint": claims.token_fingerprint,
    }


def identity_observation_human_lines(*, observation: dict[str, Any] | None) -> tuple[str, ...]:
    """Render the observation as operator-facing lines, or nothing without one."""
    if observation is None:
        return ()
    return (
        f"identity_prior_state: {observation['prior_state']}",
        f"identity_token_change: {observation['token_change']}",
        f"identity_state_path: {observation['state_path']}",
    )


def _change(
    *,
    current: str | None,
    prior_value: str | None,
    prior_present: bool,
) -> IdentityChange:
    if not prior_present:
        return "first-observation"
    return "unchanged" if current == prior_value else "changed"

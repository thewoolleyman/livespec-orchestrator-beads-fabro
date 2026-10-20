"""Explicit evidence that clears post-expiry availability uncertainty."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_hold_coverage import hold_covers_candidate
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold

__all__: list[str] = [
    "AcpAvailabilityConfirmation",
    "outstanding_confirmation_holds",
]


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilityConfirmation:
    """A successful confirmation naming only the observations it satisfied."""

    availability_key: str
    candidate_key: str
    observation_ids: frozenset[str]


def outstanding_confirmation_holds(
    *,
    expired_holds: tuple[AcpAvailabilityHold, ...],
    confirmations: tuple[AcpAvailabilityConfirmation, ...],
    candidate: AcpCandidate,
) -> tuple[AcpAvailabilityHold, ...]:
    """Return expired observations still unconfirmed for this exact candidate."""
    identity = candidate.identity
    if identity is None:
        return ()
    named = frozenset(
        observation_id
        for confirmation in confirmations
        if (confirmation.availability_key, confirmation.candidate_key) == identity.pair
        for observation_id in confirmation.observation_ids
    )
    return tuple(
        hold
        for hold in expired_holds
        if hold_covers_candidate(hold=hold, candidate=candidate)
        and hold.observation_id not in named
    )

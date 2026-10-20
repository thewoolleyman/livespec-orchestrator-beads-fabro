"""Explicit evidence that clears post-expiry availability uncertainty."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_factory_success_records import (
    FactorySuccessObservation,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_coverage import hold_covers_candidate
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import retired_by_success
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_hold_retirement import successful_attempt

__all__: list[str] = [
    "AcpAvailabilityConfirmation",
    "confirmations_for_successes",
    "outstanding_confirmation_holds",
]


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilityConfirmation:
    """A successful confirmation naming only the observations it satisfied."""

    availability_key: str
    candidate_key: str
    observation_ids: frozenset[str]


def confirmations_for_successes(
    *,
    expired_holds: tuple[AcpAvailabilityHold, ...],
    successes: tuple[FactorySuccessObservation, ...],
) -> tuple[AcpAvailabilityConfirmation, ...]:
    """Turn successful factory attempts into exact post-expiry confirmations.

    An expired hold must remain visible to selection until a later successful
    attempt confirms it.  The normal retirement predicate is deliberately
    reused here: it provides both the time ordering and the domain-or-candidate
    matching rule, while this projection retains the observation id rather than
    deleting an expired record.  Grouping only matching ids means a success
    cannot accidentally satisfy a newer observation it did not follow.
    """
    observations: dict[tuple[str, str], set[str]] = {}
    for success in successes:
        if success.candidate_key is None:
            continue
        attempt = successful_attempt(observation=success)
        confirmed = {
            hold.observation_id
            for hold in expired_holds
            if retired_by_success(hold=hold, success=attempt)
        }
        if confirmed:
            observations.setdefault(
                (success.availability_key, success.candidate_key), set()
            ).update(confirmed)
    return tuple(
        AcpAvailabilityConfirmation(
            availability_key=availability_key,
            candidate_key=candidate_key,
            observation_ids=frozenset(observation_ids),
        )
        for (availability_key, candidate_key), observation_ids in observations.items()
    )


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

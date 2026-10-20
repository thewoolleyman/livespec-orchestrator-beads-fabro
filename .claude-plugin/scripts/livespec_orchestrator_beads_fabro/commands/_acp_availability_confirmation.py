"""Explicit evidence that clears post-expiry availability uncertainty.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A candidate covered by an expired domain or candidate hold carries
an outstanding availability confirmation, and per-node selection MUST skip that
candidate until that confirmation is satisfied. ... A successful confirmation
satisfies the expired observations it names for that candidate. It MUST NOT
satisfy a newer observation."

EXPIRY ENDS A HOLD AND ESTABLISHES NOTHING, which is the whole reason this
module exists. `_acp_hold_ledger` drops an expired record from its live set,
and before this an expired observation therefore made the candidate
immediately selectable again -- so every expiry was followed by a real dispatch
that rediscovered the outage by failing. The measured outages lasted DAYS (a
reset claim of "Aug 27th" observed on Aug 23; "Oct 16th" observed on Oct 10),
while the bounded expiry is fifteen minutes, so that rediscovery was the
ordinary case rather than an edge.

THE RETIREMENT PREDICATE IS REUSED RATHER THAN RESTATED, and that is the one
decision an editor is most likely to undo. `retired_by_success` already carries
both halves of the matching rule -- the time ordering ("a node attempt that
STARTS after a domain observation"), which is exactly the clause's "MUST NOT
satisfy a newer observation", and the domain-or-candidate scoping -- so a
second account of either would be a second authority on which evidence
falsifies which record. What differs here is the DIRECTION: retirement DELETES
the record, while a confirmation must retain the observation ID, because the
clause scopes satisfaction to the observations a confirmation NAMES and a
deleted record names nothing.

A SUCCESS WHOSE ROW RECORDED NO CANDIDATE KEY CONFIRMS NOTHING, and the
asymmetry with retirement is deliberate. Such an attempt still retires the
right DOMAIN record -- `_acp_hold_ledger.AcpSuccessfulAttempt` says so -- but
availability is confirmed "only by a successfully completed ACP prompt turn
using the candidate's pinned adapter version, requested model and effort, and
projected worker credential identity", and a run that did not record WHICH
candidate ran establishes none of those properties for any candidate. So it is
passed over and the candidate keeps its outstanding confirmation, which is the
conservative direction: the cost is one confirmation turn, and the cost of the
other direction is a dispatch into a live outage on evidence nobody can
attribute.

PURE, AND HANDED ITS EVIDENCE RATHER THAN READING IT, exactly as
`_acp_candidate_preflight` and `_acp_hold_retirement` beside it are: the
expired records, the successes and the candidate all come from ONE evaluation,
so a record retiring between two reads cannot be surfaced by one half and acted
on by the other.
"""

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

    One confirmation per candidate identity, naming EVERY expired observation
    that identity's successes satisfied, because the filter below asks a
    question per candidate and a per-success record would make one candidate's
    two successes read as two different confirmations of one outage.

    A success that satisfied NO expired observation records no confirmation at
    all, rather than an empty one. Both read identically to
    `outstanding_confirmation_holds`, and the empty form is the shape that
    tempts a later reader into treating the record's existence as evidence --
    which would clear the very observations it names none of.
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
    """Return expired observations still unconfirmed for this exact candidate.

    An IDENTITY-LESS candidate has no outstanding confirmation, for the reason
    `_acp_candidate_preflight._evidence_unconfirmed` gives one venue over: such
    an adapter belongs to no typed domain, so no typed observation can be about
    it, and skipping it here would strand the one adapter shape the contract
    allows to carry no identity. Its conservative legacy posture -- covered by
    every live legacy record -- is unchanged.

    A confirmation is matched on the candidate's EXACT identity pair, never on
    the hold's own scope, which is what makes a DOMAIN observation outstanding
    for each covered candidate separately: the clause satisfies the expired
    observations a confirmation names "for that candidate", so one candidate's
    successful turn says nothing about a sibling sharing its allowance.
    """
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

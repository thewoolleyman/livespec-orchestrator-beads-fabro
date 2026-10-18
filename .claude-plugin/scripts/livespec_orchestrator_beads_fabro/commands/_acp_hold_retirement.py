"""Applying the retirement routes to ONE host-wide union of availability records.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Bounded expiry, later matching execution, and operator clearance
are the only hold-retirement routes." `_acp_hold_ledger` applies all three to
the records its own JOURNAL carries; this applies the two that are not bounded
expiry to the UNION of that fold with the host-wide factory read, which is the
only place both halves are in hand at once.

TWO RETIREMENTS, AND NEITHER IS A SPECIAL CASE OF THE OTHER. A later matching
SUCCESS, read from the factory's own run records, falsifies a record by the
clause's own matching rule -- `retired_by_success` owns that decision and is
imported rather than restated. An OPERATOR CLEARANCE, or an already-journalled
success retirement, names observation ids, and those ids must reach the
FACTORY-DERIVED half too: a derived record carries the same `observation_id` a
projection of the same evidence would, because that id digests the evidence
plus the scope it lands on, so a retirement line naming it is naming this
record. Appending the union raw was what left an operator's exact clearance
unable to retire the very record the factory kept re-deriving.

THE DECISION LIVES WHERE THE RECORDS MEET, AND THE PRODUCERS STAY IGNORANT OF
IT. `_acp_factory_hold_evidence` cannot be handed a journal -- that absence is
what makes hold observations "reconstructible after any repository-local
dispatch journal is removed" structurally rather than carefully -- so it can
neither read a retirement line nor filter itself by one. And the journal fold
cannot see a factory, so it can neither derive a success nor know that one
exists. Keeping the join here is what lets both stay true.

PURE, AND HANDED ITS EVIDENCE RATHER THAN READING IT, exactly as the wait
derivation beside it is: the holds, the successes and the retired ids all come
from ONE evaluation, so a record retiring between two reads cannot be surfaced
by one half and acted on by the other.

RETIREMENT IS THE DESTRUCTIVE DIRECTION, and every arm that cannot decide keeps
the record. `retired_by_success` already reports False for an unreadable clock
on either side, which is why no such arm appears here: a hold nobody could date
survives, and the record that survives is the one that keeps work away from a
live outage.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_factory_success_records import (
    FactorySuccessObservation,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import (
    AcpSuccessfulAttempt,
    retired_by_success,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold

__all__: list[str] = [
    "retained_holds",
    "successful_attempt",
]


def successful_attempt(*, observation: FactorySuccessObservation) -> AcpSuccessfulAttempt:
    """The retirement evidence one derived SUCCESS stands for.

    The domain set is the single allowance the run recorded, for the reason
    `_acp_factory_success_records` gives: a peer candidate's declared domain
    overrides are the declaring repository's configuration, and a derived
    attempt must not claim an allowance nobody recorded it spending.
    """
    return AcpSuccessfulAttempt(
        availability_key=observation.availability_key,
        candidate_key=observation.candidate_key,
        domain_keys=frozenset({observation.availability_key}),
        started_at=observation.started_at,
    )


def retained_holds(
    *,
    holds: tuple[AcpAvailabilityHold, ...],
    successes: tuple[FactorySuccessObservation, ...],
    retired_observation_ids: frozenset[str],
) -> tuple[AcpAvailabilityHold, ...]:
    """Every record of this union that no retirement route has falsified.

    Order is preserved, because the candidate filter reads these in sequence
    and the wait derivation reports the FIRST matching record for an emptied
    node; a filter that reordered them would change which observation a
    refusal names without changing any decision it makes.
    """
    attempts = tuple(successful_attempt(observation=observation) for observation in successes)
    return tuple(
        hold
        for hold in holds
        if hold.observation_id not in retired_observation_ids
        and not any(retired_by_success(hold=hold, success=attempt) for attempt in attempts)
    )

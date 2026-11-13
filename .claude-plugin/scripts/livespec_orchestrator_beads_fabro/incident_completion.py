"""Final normal incident proof: what every acceptance and closure path requires.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" and its
scenario "incident completion requires final normal proof rather than an old
repair merge". An incident item may close only once its retained chain records
`closed`, and `complete_incident` records `closed` only when the current normal
factory repayment PR merged, its normal master CI succeeded, the marker is gone,
the manual outcome is recorded, every cumulative original path was validated,
every deferred verification and spec debt was repaid, and related failures were
disposed. Each closure route reads `read_incident_standing` and refuses while it
names an outstanding obligation; acceptance grades the original expedited
carriers together with the current repayment carrier (`incident_acceptance_scope`).
A normal item, with no incident genesis, is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_completion_rules import (
    CLOSED_PHASE,
    COMPLETION_PHASE,
    DRILL_CLOSED_OBLIGATION,
    DRILL_CLOSED_PHASE,
    IncidentAcceptanceScope,
    IncidentCompletionEvidence,
    acceptance_scope,
    completion_obligations,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_completion_reader import (
    IncidentStanding,
    read_incident_standing,
)
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    require_repayment_current,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "CLOSED_PHASE",
    "COMPLETION_PHASE",
    "DRILL_CLOSED_OBLIGATION",
    "DRILL_CLOSED_PHASE",
    "IncidentAcceptanceScope",
    "IncidentCompletion",
    "IncidentCompletionEvidence",
    "IncidentStanding",
    "complete_incident",
    "completion_obligations",
    "incident_acceptance_scope",
    "incident_effect_refusal",
    "read_incident_standing",
]


@dataclass(frozen=True, kw_only=True)
class IncidentCompletion:
    """One completion attempt: recorded `closed`, or the obligations still outstanding."""

    item_id: str
    recorded: bool
    recovered: bool
    outstanding: tuple[str, ...]
    reading: IncidentReading | None = None


def incident_acceptance_scope(
    *, standing: IncidentStanding, merged_pr: int | None
) -> IncidentAcceptanceScope | None:
    """What one acceptance pass of this item grades; None for a normal item."""
    if standing.kind == "normal":
        return None
    if standing.kind == "unreadable":
        return IncidentAcceptanceScope(
            item_id=standing.item_id,
            original_prs=(),
            current_pr=None,
            refusal=f"incident standing unreadable: {'; '.join(standing.outstanding)}",
        )
    return acceptance_scope(history=standing.history, merged_pr=merged_pr)


def complete_incident(
    *, client: BeadsClient, item_id: str, evidence: IncidentCompletionEvidence
) -> IncidentCompletion | AuthorityRefusal:
    """Record the incident `closed` once nothing is outstanding, or name what is.

    The evidence is what was observed; anything not observed stays an
    obligation. A repeated delivery after `closed` recovers it and writes
    nothing. The `closed` generation is committed through the same retained
    conditional-close writer as every other phase, after the observed repayment
    generation is revalidated (`require_repayment_current`), so a superseded or
    stale observation records nothing.
    """
    standing = read_incident_standing(client=client, item_id=item_id)
    if standing.kind == "normal":
        return AuthorityRefusal(code="incident-authority-missing", detail=item_id)
    if standing.kind == "unreadable" or standing.reading is None:
        return AuthorityRefusal(
            code="incident-completion-unreadable", detail="; ".join(standing.outstanding)
        )
    outstanding = completion_obligations(history=standing.history, evidence=evidence)
    if outstanding:
        return IncidentCompletion(
            item_id=item_id, recorded=False, recovered=False, outstanding=outstanding
        )
    current = standing.reading.attempt
    if current.phase == CLOSED_PHASE:
        return IncidentCompletion(item_id=item_id, recorded=True, recovered=True, outstanding=())
    # The repayment generation the evidence was judged against must still be the
    # chain's head: a regression that reopened the item supersedes it.
    observed = require_repayment_current(client=client, observed=standing.reading, effect="closure")
    committed = (
        observed
        if isinstance(observed, AuthorityRefusal)
        else commit_transition(
            client=client,
            observed=observed,
            successor=replace(
                current,
                phase=CLOSED_PHASE,
                operation_id=f"{current.attempt_id}#{CLOSED_PHASE}",
                generation=current.generation + 1,
            ),
        )
    )
    if isinstance(committed, AuthorityRefusal):
        return committed
    return IncidentCompletion(
        item_id=item_id, recorded=True, recovered=False, outstanding=(), reading=committed
    )


def incident_effect_refusal(
    *, client: BeadsClient, standing: IncidentStanding, effect: Literal["merge", "proof", "closure"]
) -> AuthorityRefusal | None:
    """Revalidate the generation `standing` observed, right before `effect`.

    A repayment generation the chain has since moved past is refused
    `incident-repayment-superseded`, any other moved generation
    `incident-generation-stale`; a normal item has no generation to revalidate.
    """
    if standing.reading is None:
        return None
    current = require_repayment_current(client=client, observed=standing.reading, effect=effect)
    return current if isinstance(current, AuthorityRefusal) else None

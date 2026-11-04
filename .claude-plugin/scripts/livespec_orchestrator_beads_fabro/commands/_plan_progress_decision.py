"""What one sanctioned plan pointer write is allowed to do to the obligation.

PURE over the observed chain head, the candidate pointer and the reading of the
prior obligation's target. Every effect — the chain transition, the handoff
comment, the pointer write — belongs to `_plan_tracked_write`, which is what
makes each branch here exercisable without a store or a factory.

`contracts.md` section "Required result, budget and progress epoch" names the
cases and this module is exactly those:

- NO PRIOR OBLIGATION — the candidate's own budget becomes the original.
- A SATISFIED result — "Satisfied results permit advancing to a new result and
  budget", so the candidate's budget becomes the original for a fresh epoch.
- AN UNSATISFIED or UNOBSERVABLE result — handed to `_plan_progress_unmet`, which
  continues the obligation (an accepted handoff consumes one unit, a direct
  pointer write none) or replaces its result. Neither limit is ever a reason to
  refuse: the budget is a reporting datum only, and the expiry rule it once
  enforced was deleted on the maintainer's 2026-11-03 ruling.

THE SATISFIED AND UNOBSERVABLE ARMS ARE NOT INTERCHANGEABLE, which is why the
observation's status is read rather than its truthiness. `satisfied` advances to
a fresh epoch on the strength of the reading; `unobservable` is a failure to
MEASURE, so it continues or replaces exactly as an unmet result does and never
counts as completion: "Unobservable results MUST refuse any transition claiming
completion".

WHY A PICKER WRITE RETAINS THE OBLIGATION INSTEAD OF CLEARING IT. "For `human`
and `none`, both tracking fields MUST be explicit null, and changing to them
MUST retain any unmet obligation in the progress history." So the POINTER goes
null while the AUTHORITY keeps the obligation — the two diverge deliberately,
and clearing the authority is how an unmet result would be discharged by simply
pointing somewhere else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    CandidateBudget,
    candidate_budget,
    obligation_of,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_outcome import (
    EVENT_HANDOFF,
    EVENT_PICKER,
    EVENT_POINTER,
    TrackedDecision,
    TrackedRefusal,
    retained_authority,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_unmet import unmet_decision
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_obligation import Obligation
    from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )

__all__: list[str] = [
    "decide_tracked_write",
]


def decide_tracked_write(  # noqa: PLR0913 -- kw-only; each input is an independent fact of the write.
    *,
    epic_id: str,
    head: ChainHead,
    candidate: NextAction,
    now: str,
    is_handoff: bool,
    observation: ResultObservation | None,
    recovery: CausalRecovery | None = None,
) -> TrackedDecision | TrackedRefusal:
    """Decide what one write may do to the obligation the chain holds.

    `observation` is the reading of the PRIOR obligation's target, taken by the
    caller because it is the one input here that needs a store. It is `None`
    exactly when there is no prior obligation to read.
    """
    prior = obligation_of(authority=head.authority)
    consumed = int(is_handoff)
    claim = _recovery_claim_refusal(prior=prior, recovery=recovery, observation=observation)
    if claim is not None:
        return claim
    if candidate.required_result is None:
        return _picker_decision(
            candidate=candidate,
            prior=prior,
            consumed=consumed,
            attempt=head.authority.last_recovery_attempt,
        )
    proposed = candidate_budget(budget=candidate.budget)
    if proposed is None:
        return TrackedRefusal(detail="budget must carry a deadline and positive max_handoffs")
    if prior is None or observation is None or observation.status == OBSERVATION_SATISFIED:
        return _fresh_decision(candidate=candidate, proposed=proposed, consumed=consumed)
    return unmet_decision(
        epic_id=epic_id,
        head=head,
        candidate=candidate,
        proposed=proposed,
        prior=prior,
        consumed=consumed,
        is_handoff=is_handoff,
        recovery=recovery,
        now=now,
    )


def _recovery_claim_refusal(
    *,
    prior: Obligation | None,
    recovery: CausalRecovery | None,
    observation: ResultObservation | None,
) -> TrackedRefusal | None:
    """Refuse a recovery attempt no unmet obligation can answer.

    An attempt is ABOUT an obligation that stands unmet, so an epic holding none,
    or one whose result is already satisfied, has nothing for it to recover.
    """
    if recovery is None:
        return None
    if prior is None:
        return TrackedRefusal(
            detail="causal recovery is invalid: no obligation stands that could be recovered"
        )
    if observation is None or observation.status == OBSERVATION_SATISFIED:
        return TrackedRefusal(
            detail="causal recovery is invalid: the obligation's result is already satisfied"
        )
    return None


def _picker_decision(
    *,
    candidate: NextAction,
    prior: Obligation | None,
    consumed: int,
    attempt: object = None,
) -> TrackedDecision:
    """A `human` or `none` pointer: null tracking, obligation retained."""
    if prior is None:
        return TrackedDecision(
            action=candidate,
            authority=AuthorityState(),
            event_kind=EVENT_PICKER,
        )
    return TrackedDecision(
        action=candidate,
        authority=retained_authority(prior=prior, consumed=consumed, attempt=attempt),
        event_kind=EVENT_PICKER,
    )


def _fresh_decision(
    *,
    candidate: NextAction,
    proposed: CandidateBudget,
    consumed: int,
) -> TrackedDecision:
    """Begin a new obligation under the candidate's own budget."""
    return TrackedDecision(
        action=candidate,
        authority=AuthorityState(
            required_result=candidate.required_result,
            original_deadline=proposed.deadline,
            max_handoffs=proposed.max_handoffs,
            consumed_handoffs=consumed,
        ),
        event_kind=EVENT_HANDOFF if consumed else EVENT_POINTER,
    )

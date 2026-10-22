"""What one sanctioned plan pointer write is allowed to do to the obligation.

PURE over the observed chain head, the candidate pointer and the reading of the
prior obligation's target. Every effect — the chain transition, the handoff
comment, the pointer write — belongs to `_plan_tracked_write`, which is what
makes each branch here exercisable without a store or a factory.

`contracts.md` section "Required result, budget and progress epoch" names four
cases and this module is exactly those four:

- NO PRIOR OBLIGATION — the candidate's own budget becomes the original.
- A SATISFIED result — "Satisfied results permit advancing to a new result and
  budget", so the candidate's budget becomes the original for a fresh epoch.
- AN UNSATISFIED result — the prior obligation is PRESERVED whole, and an
  accepted handoff consumes one unit while a direct pointer write consumes none.
- AN UNOBSERVABLE result — "Unobservable results MUST preserve the original
  budget and refuse any transition claiming completion", so the prior obligation
  is preserved exactly as in the unsatisfied case, and advancing is refused.

THE SATISFIED AND UNOBSERVABLE ARMS ARE NOT INTERCHANGEABLE, which is why the
observation's status is read rather than its truthiness. `satisfied` is the one
arm permitted to replace the budget; `unobservable` is a failure to MEASURE and
must not be allowed to, because a result nobody could read is the cheapest
possible way to earn a fresh deadline. Collapsing them gives an obligation a new
budget every time its reader is broken.

THE TWO UNMET ARMS LIVE IN `_plan_progress_unmet`, which is the half of the
ladder every refusal lives in: the rename refusal, the expiry gate, the typed
causal recovery and the evidenced causal supersession all defend a budget that
already stands, while the arms kept here ESTABLISH one. This module is the
DISPATCH and nothing more — it decides which of the clause's four cases a write
is in, and hands an unmet obligation to the module that defends it.

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
from livespec_orchestrator_beads_fabro.commands._plan_progress_unmet import (
    continuation_decision,
    superseded_decision,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_obligation import Obligation
    from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
        CausalSupersession,
        SupersessionEvidence,
    )

__all__: list[str] = [
    "decide_tracked_write",
]


def decide_tracked_write(  # noqa: PLR0911, PLR0913 -- one refusal ladder; a merged arm would report the wrong cause.
    *,
    epic_id: str,
    head: ChainHead,
    candidate: NextAction,
    now: str,
    is_handoff: bool,
    observation: ResultObservation | None,
    recovery: CausalRecovery | None = None,
    supersession: CausalSupersession | None = None,
    evidence: SupersessionEvidence | None = None,
) -> TrackedDecision | TrackedRefusal:
    """Decide what one write may do, preserving an unmet obligation's budget.

    `observation` is the reading of the PRIOR obligation's target, taken by the
    caller because it is the one input here that needs a store. It is `None`
    exactly when there is no prior obligation to read. `evidence` is the same
    kind of input for the supersession's own cause, and is `None` exactly when no
    supersession is carried.
    """
    prior = obligation_of(authority=head.authority)
    consumed = int(is_handoff)
    claim = _claim_refusal(prior=prior, recovery=recovery, supersession=supersession)
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
    if prior is None:
        return _fresh_decision(candidate=candidate, proposed=proposed, consumed=consumed)
    if observation is None or observation.status == OBSERVATION_SATISFIED:
        settled = _satisfied_refusal(recovery=recovery, supersession=supersession)
        if settled is not None:
            return settled
        return _fresh_decision(candidate=candidate, proposed=proposed, consumed=consumed)
    if supersession is not None:
        return superseded_decision(
            head=head,
            candidate=candidate,
            prior=prior,
            supersession=supersession,
            evidence=evidence,
            now=now,
        )
    return continuation_decision(
        epic_id=epic_id,
        head=head,
        candidate=candidate,
        prior=prior,
        consumed=consumed,
        unobservable=observation.status == OBSERVATION_UNOBSERVABLE,
        is_handoff=is_handoff,
        recovery=recovery,
        now=now,
    )


def _claim_refusal(
    *,
    prior: Obligation | None,
    recovery: CausalRecovery | None,
    supersession: CausalSupersession | None,
) -> TrackedRefusal | None:
    """Refuse a claim no obligation can answer, before any arm is chosen.

    Both claims are ABOUT an obligation that stands — a recovery reopens an
    expired one and a supersession replaces an unmet one — so an epic holding
    none can answer neither, and a write carrying both answers neither either:
    they are different questions about one obligation, and grading them together
    would leave whichever ran second ungraded while the write reported success.
    """
    if recovery is not None and supersession is not None:
        return TrackedRefusal(
            detail=(
                "one write carries either a typed causal recovery or an evidenced causal"
                " supersession, never both: they answer different questions about the same"
                " obligation and a write claiming each would leave neither graded"
            )
        )
    if prior is not None:
        return None
    if recovery is not None:
        return TrackedRefusal(detail="causal recovery is invalid: no obligation is not expired")
    if supersession is not None:
        return TrackedRefusal(
            detail="a supersession is invalid: no obligation stands that could be replaced"
        )
    return None


def _satisfied_refusal(
    *,
    recovery: CausalRecovery | None,
    supersession: CausalSupersession | None,
) -> TrackedRefusal | None:
    """Refuse either claim against a SATISFIED obligation.

    A satisfied result already "permits advancing to a new result and budget",
    so neither claim has anything to do: a recovery would be reopening an
    obligation that is not expired, and a supersession would be renaming one the
    ordinary advance replaces anyway — which is the one shape in which a
    supersession could carry a budget of the caller's own choosing.
    """
    if recovery is not None:
        return TrackedRefusal(
            detail="causal recovery is invalid: a satisfied obligation is not expired"
        )
    if supersession is not None:
        return TrackedRefusal(
            detail=(
                "a supersession is invalid: the obligation is satisfied, so the ordinary"
                " advance already permits a new result and budget"
            )
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

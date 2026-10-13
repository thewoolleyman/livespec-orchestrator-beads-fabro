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

WHY A RENAMED RESULT IS REFUSED RATHER THAN ACCEPTED AS NEW WORK. The clause:
"A replacement or renaming of an unmet result MUST preserve the original
obligation and deadline until an evidenced causal supersession explicitly
accounts for it; a new label, repair-child milestone, acknowledgment or
changed-approach claim cannot evade expiry." Renaming the target is the one
rewrite that would otherwise look like legitimate advancement, because the
pointer it produces is indistinguishable from a genuinely new obligation.

WHY A PICKER WRITE RETAINS THE OBLIGATION INSTEAD OF CLEARING IT. "For `human`
and `none`, both tracking fields MUST be explicit null, and changing to them
MUST retain any unmet obligation in the progress history." So the POINTER goes
null while the AUTHORITY keeps the obligation — the two diverge deliberately,
and clearing the authority is how an unmet result would be discharged by simply
pointing somewhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    CandidateBudget,
    Obligation,
    candidate_budget,
    obligation_of,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )

__all__: list[str] = [
    "EVENT_HANDOFF",
    "EVENT_PICKER",
    "EVENT_POINTER",
    "TrackedDecision",
    "TrackedRefusal",
    "decide_tracked_write",
]

EVENT_HANDOFF = "handoff"
EVENT_POINTER = "pointer"
EVENT_PICKER = "picker"


@dataclass(frozen=True, kw_only=True)
class TrackedDecision:
    """The authority to commit and the pointer that projects it."""

    action: NextAction
    authority: AuthorityState
    event_kind: str


@dataclass(frozen=True, kw_only=True)
class TrackedRefusal:
    """Why one sanctioned write was refused BEFORE it mutated anything."""

    detail: str


def decide_tracked_write(
    *,
    head: ChainHead,
    candidate: NextAction,
    now: str,
    is_handoff: bool,
    observation: ResultObservation | None,
) -> TrackedDecision | TrackedRefusal:
    """Decide what one write may do, preserving an unmet obligation's budget.

    `observation` is the reading of the PRIOR obligation's target, taken by the
    caller because it is the one input here that needs a store. It is `None`
    exactly when there is no prior obligation to read.
    """
    _ = now
    prior = obligation_of(authority=head.authority)
    consumed = int(is_handoff)
    if candidate.required_result is None:
        return _picker_decision(candidate=candidate, prior=prior, consumed=consumed)
    proposed = candidate_budget(budget=candidate.budget)
    if proposed is None:
        return TrackedRefusal(detail="budget must carry a deadline and positive max_handoffs")
    if prior is None:
        return _fresh_decision(candidate=candidate, proposed=proposed, consumed=consumed)
    if observation is None or observation.status == OBSERVATION_SATISFIED:
        return _fresh_decision(candidate=candidate, proposed=proposed, consumed=consumed)
    return _continuation_decision(
        candidate=candidate,
        prior=prior,
        consumed=consumed,
        unobservable=observation.status == OBSERVATION_UNOBSERVABLE,
        is_handoff=is_handoff,
    )


def _picker_decision(
    *,
    candidate: NextAction,
    prior: Obligation | None,
    consumed: int,
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
        authority=_retained(prior=prior, consumed=consumed),
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


def _continuation_decision(
    *,
    candidate: NextAction,
    prior: Obligation,
    consumed: int,
    unobservable: bool,
    is_handoff: bool,
) -> TrackedDecision | TrackedRefusal:
    """Continue an unmet obligation, preserving both of its original limits."""
    refusal = _same_result_refusal(candidate=candidate, prior=prior, unobservable=unobservable)
    if refusal is not None:
        return refusal
    return TrackedDecision(
        action=replace(candidate, required_result=prior.required_result),
        authority=_retained(prior=prior, consumed=consumed),
        event_kind=EVENT_HANDOFF if is_handoff else EVENT_POINTER,
    )


def _same_result_refusal(
    *,
    candidate: NextAction,
    prior: Obligation,
    unobservable: bool,
) -> TrackedRefusal | None:
    """Refuse a rewrite that renames the unmet target it is continuing."""
    candidate_parsed = parse_result_reference(value=candidate.required_result)
    prior_parsed = parse_result_reference(value=prior.required_result)
    if not isinstance(candidate_parsed, ResultReference):
        return TrackedRefusal(detail="required_result is not a typed reference")
    if not isinstance(prior_parsed, ResultReference):
        return TrackedRefusal(
            detail="the prior obligation's required_result is unreadable; reconcile it first"
        )
    if candidate_parsed.identity == prior_parsed.identity:
        return None
    if unobservable:
        return TrackedRefusal(
            detail=(
                f"the obligation {prior_parsed.identity} is unobservable, so it cannot be"
                f" replaced by {candidate_parsed.identity}"
            )
        )
    return TrackedRefusal(
        detail=(
            f"the unmet obligation {prior_parsed.identity} cannot be renamed to"
            f" {candidate_parsed.identity} without evidenced causal supersession"
        )
    )


def _retained(*, prior: Obligation, consumed: int) -> AuthorityState:
    """The prior obligation, with only its accepted-handoff count advanced."""
    return AuthorityState(
        required_result=prior.required_result,
        original_deadline=prior.original_deadline,
        max_handoffs=prior.max_handoffs,
        consumed_handoffs=prior.consumed_handoffs + consumed,
    )

"""What one sanctioned write may do to an obligation that is still UNMET.

PURE. `_plan_progress_decision` keeps the DISPATCH plus the arms for an
obligation that is absent, satisfied or null-tracked; this module is the arm for
an unmet one, which a write either CONTINUES or REPLACES.

AN OVERDUE OBLIGATION IS NEVER A REASON TO REFUSE. `contracts.md` section
"Required result, budget and progress epoch" makes the budget a reporting datum
only: "being overdue MUST NOT cause any write to be refused, any continuation to
require a recovery attempt, a continuation ruling or a human decision, or any
executable action to be withheld." So nothing here reads the clock or the
handoff ceiling. That is the deletion of the expiry rule the maintainer ordered
on 2026-11-03 ("Whatever 'stall' rule is in effect here, completely delete it"),
and it is a deletion rather than a toggle: there is no arm left that could
refuse on a limit.

A RENAMED RESULT IS A REPLACEMENT, NOT A REFUSAL. "A sanctioned write MAY replace
an unmet result with a different typed required result. The replacement MUST be
recorded as a `plan-progress-event` of kind `replacement` ... the new obligation
begins under the write's own budget." The rename refusal and the evidenced
supersession it demanded existed only to stop a rename from evading expiry, so
with expiry gone they were pure stall rules: a stale target could never be
re-aimed.

A TYPED CAUSAL RECOVERY ATTEMPT IS OPTIONAL. "no write requires one", but one
that IS carried is still graded and recorded, because the independent consumer
executes the operation it names and an unvalidated record must not become one.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_progress_outcome import (
    EVENT_HANDOFF,
    EVENT_POINTER,
    EVENT_RECOVERY,
    EVENT_REPLACEMENT,
    TrackedDecision,
    TrackedRefusal,
    retained_authority,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    recovery_record,
    validate_causal_recovery,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
        CandidateBudget,
        Obligation,
    )
    from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery

__all__: list[str] = [
    "unmet_decision",
]


def unmet_decision(  # noqa: PLR0913 -- an unmet write needs every prior and candidate fact.
    *,
    epic_id: str,
    head: ChainHead,
    candidate: NextAction,
    proposed: CandidateBudget,
    prior: Obligation,
    consumed: int,
    is_handoff: bool,
    recovery: CausalRecovery | None,
    now: str,
) -> TrackedDecision | TrackedRefusal:
    """Continue an unmet obligation, or replace its result, whatever its limits read."""
    identities = _result_identities(candidate=candidate, prior=prior)
    if isinstance(identities, TrackedRefusal):
        return identities
    candidate_identity, prior_identity = identities
    if candidate_identity != prior_identity:
        if recovery is not None:
            return TrackedRefusal(
                detail=(
                    "a typed causal recovery attempt names the obligation it recovers, so it"
                    " cannot ride on a write that replaces that obligation's result"
                )
            )
        return _replacement_decision(
            candidate=candidate,
            proposed=proposed,
            consumed=consumed,
            head=head,
            replaced_identity=prior_identity,
        )
    attempt = head.authority.last_recovery_attempt
    if recovery is not None:
        recovery_refusal = validate_causal_recovery(
            recovery=recovery,
            action=candidate,
            epic_id=epic_id,
            current_epoch=head.epoch,
            current_result_identity=prior_identity,
            now=now,
        )
        if recovery_refusal is not None:
            return TrackedRefusal(detail=recovery_refusal.detail)
        attempt = recovery_record(recovery=recovery, prior=head.authority, now=now)
    return TrackedDecision(
        action=replace(candidate, required_result=prior.required_result),
        authority=retained_authority(prior=prior, consumed=consumed, attempt=attempt),
        event_kind=_event_kind(recovery=recovery, is_handoff=is_handoff),
    )


def _event_kind(*, recovery: CausalRecovery | None, is_handoff: bool) -> str:
    if recovery is not None:
        return EVENT_RECOVERY
    return EVENT_HANDOFF if is_handoff else EVENT_POINTER


def _result_identities(
    *,
    candidate: NextAction,
    prior: Obligation,
) -> tuple[str, str] | TrackedRefusal:
    """The candidate's and the prior obligation's canonical result identities."""
    candidate_parsed = parse_result_reference(value=candidate.required_result)
    prior_parsed = parse_result_reference(value=prior.required_result)
    if not isinstance(candidate_parsed, ResultReference):
        return TrackedRefusal(detail="required_result is not a typed reference")
    if not isinstance(prior_parsed, ResultReference):
        return TrackedRefusal(
            detail="the prior obligation's required_result is unreadable; reconcile it first"
        )
    return candidate_parsed.identity, prior_parsed.identity


def _replacement_decision(
    *,
    candidate: NextAction,
    proposed: CandidateBudget,
    consumed: int,
    head: ChainHead,
    replaced_identity: str,
) -> TrackedDecision:
    """Begin a new obligation under the write's own budget, recording the replacement.

    The replaced obligation is not erased: the chain keeps the transition that
    held it, and the `replacement` event kind names it in the progress history.
    The item-attributable recovery record is carried forward, because that count
    is a fact about the item's dispatches rather than about which result the plan
    is currently waiting on.
    """
    return TrackedDecision(
        action=candidate,
        authority=AuthorityState(
            required_result=candidate.required_result,
            original_deadline=proposed.deadline,
            max_handoffs=proposed.max_handoffs,
            consumed_handoffs=consumed,
            last_recovery_attempt=head.authority.last_recovery_attempt,
        ),
        event_kind=EVENT_REPLACEMENT,
        replaced_result=replaced_identity,
    )

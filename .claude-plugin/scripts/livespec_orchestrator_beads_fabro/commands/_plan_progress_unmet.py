"""What one sanctioned write may do to an obligation that is still UNMET.

PURE, and the half of the decision ladder every refusal lives in: an unmet
obligation is the state in which the clause's guarantees bite, so this is where
the rename refusal, the expiry gate, the typed causal recovery and the evidenced
causal supersession are graded. `_plan_progress_decision` keeps the DISPATCH plus
the arms for an obligation that is absent, satisfied or null-tracked, which are
the arms that establish a budget rather than defend one.

WHY A RENAMED RESULT IS REFUSED RATHER THAN ACCEPTED AS NEW WORK. The clause:
"A replacement or renaming of an unmet result MUST preserve the original
obligation and deadline until an evidenced causal supersession explicitly
accounts for it; a new label, repair-child milestone, acknowledgment or
changed-approach claim cannot evade expiry." Renaming the target is the one
rewrite that would otherwise look like legitimate advancement, because the
pointer it produces is indistinguishable from a genuinely new obligation.

AND WHY THE SUPERSESSION ARM SITS BESIDE THAT REFUSAL RATHER THAN AROUND IT. The
two are one decision about one write: either the rename is evidenced, in which
case the obligation's RESULT changes while both of its limits stand, or it is
not, in which case the obligation stands whole. Splitting them across modules is
how a build comes to admit a rename on one path that the other still refuses.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_obligation import obligation_expiry
from livespec_orchestrator_beads_fabro.commands._plan_progress_outcome import (
    EVENT_HANDOFF,
    EVENT_POINTER,
    EVENT_RECOVERY,
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
from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
    EVENT_SUPERSESSION,
    validate_causal_supersession,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_obligation import Obligation
    from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
    from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
        CausalSupersession,
        SupersessionEvidence,
    )

__all__: list[str] = [
    "continuation_decision",
    "superseded_decision",
]


def continuation_decision(  # noqa: PLR0913 -- continuation needs every prior and candidate fact.
    *,
    epic_id: str,
    head: ChainHead,
    candidate: NextAction,
    prior: Obligation,
    consumed: int,
    unobservable: bool,
    is_handoff: bool,
    recovery: CausalRecovery | None,
    now: str,
) -> TrackedDecision | TrackedRefusal:
    """Continue an unmet obligation, preserving both of its original limits.

    THE EXPIRY GATE RUNS HERE, before the decision returns anything a caller
    could write: "After expiry, same-obligation continuation MUST be refused
    before appending a handoff or updating the pointer unless a fresh typed
    causal recovery attempt is supplied."
    """
    same_result = _same_result_refusal(candidate=candidate, prior=prior, unobservable=unobservable)
    if isinstance(same_result, TrackedRefusal):
        return same_result
    expiry = obligation_expiry(obligation=prior, now=now)
    if expiry is None and recovery is not None:
        return TrackedRefusal(detail="causal recovery is invalid: the obligation is not expired")
    if expiry is not None and recovery is None:
        return TrackedRefusal(
            detail=(
                f"the obligation {prior.original_deadline} is expired at its {expiry} limit;"
                " a fresh typed causal recovery attempt or a recorded human decision is"
                " required to continue"
            )
        )
    attempt = None
    if recovery is not None:
        recovery_refusal = validate_causal_recovery(
            recovery=recovery,
            action=candidate,
            epic_id=epic_id,
            current_epoch=head.epoch,
            current_result_identity=same_result,
            now=now,
        )
        if recovery_refusal is not None:
            return TrackedRefusal(detail=recovery_refusal.detail)
        attempt = recovery_record(recovery=recovery, prior=head.authority, now=now)
    return TrackedDecision(
        action=replace(candidate, required_result=prior.required_result),
        authority=retained_authority(
            prior=prior,
            consumed=consumed,
            attempt=head.authority.last_recovery_attempt if attempt is None else attempt,
        ),
        event_kind=_event_kind(recovery=recovery, is_handoff=is_handoff),
    )


def _event_kind(*, recovery: CausalRecovery | None, is_handoff: bool) -> str:
    if recovery is not None:
        return EVENT_RECOVERY
    return EVENT_HANDOFF if is_handoff else EVENT_POINTER


def _same_result_refusal(
    *,
    candidate: NextAction,
    prior: Obligation,
    unobservable: bool,
) -> TrackedRefusal | str:
    """Refuse a rewrite that renames the unmet target, or return that target.

    The PRIOR IDENTITY is returned rather than merely validated, because the
    recovery check downstream needs exactly the identity this arm has already
    parsed. Re-deriving it there would mean a second parse whose failure arm is
    unreachable — and an unreachable arm is either dead code or a lie about
    which of the two readings is authoritative.
    """
    candidate_parsed = parse_result_reference(value=candidate.required_result)
    prior_parsed = parse_result_reference(value=prior.required_result)
    if not isinstance(candidate_parsed, ResultReference):
        return TrackedRefusal(detail="required_result is not a typed reference")
    if not isinstance(prior_parsed, ResultReference):
        return TrackedRefusal(
            detail="the prior obligation's required_result is unreadable; reconcile it first"
        )
    if candidate_parsed.identity == prior_parsed.identity:
        return prior_parsed.identity
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


def superseded_decision(
    *,
    head: ChainHead,
    candidate: NextAction,
    prior: Obligation,
    supersession: CausalSupersession,
    evidence: SupersessionEvidence | None,
    now: str,
) -> TrackedDecision | TrackedRefusal:
    """Replace an unmet obligation's result, keeping BOTH of its original limits.

    THE EXPIRY RULES STILL BIND, which the clause says in as many words: "A
    supersession of an already expired obligation remains subject to the expiry
    rules above." So an expired obligation is refused here exactly as it is on
    the ordinary continuation path — a supersession is not a second route past a
    deadline.

    THE REPLACEMENT INHERITS THE ORIGINAL DEADLINE AND THE CONSUMED COUNT
    UNCHANGED, and consumes nothing: "A supersession never consumes a handoff
    unit and never resets or postpones either limit." The candidate's own budget
    is DISCARDED — a supersession that adopted it would be the laundering route
    the whole cause exists to close, and the pointer it produced would be
    indistinguishable from a legitimately advanced one.

    THE PRIOR IDENTITY IS PARSED HERE rather than taken from the caller, because
    the supersession must name the obligation the CHAIN holds and a caller-supplied
    identity is one the caller could have chosen to match.
    """
    expiry = obligation_expiry(obligation=prior, now=now)
    if expiry is not None:
        return TrackedRefusal(
            detail=(
                f"the obligation {prior.original_deadline} is expired at its {expiry} limit;"
                " a supersession does not reopen it, so a fresh typed causal recovery"
                " attempt or a recorded human decision is required first"
            )
        )
    prior_parsed = parse_result_reference(value=prior.required_result)
    if not isinstance(prior_parsed, ResultReference):
        return TrackedRefusal(
            detail="the prior obligation's required_result is unreadable; reconcile it first"
        )
    refusal = validate_causal_supersession(
        supersession=supersession,
        evidence=evidence,
        prior_identity=prior_parsed.identity,
        current_epoch=head.epoch,
        replacement=candidate.required_result,
    )
    if refusal is not None:
        return TrackedRefusal(detail=refusal.detail)
    return TrackedDecision(
        action=candidate,
        authority=AuthorityState(
            required_result=candidate.required_result,
            original_deadline=prior.original_deadline,
            max_handoffs=prior.max_handoffs,
            consumed_handoffs=prior.consumed_handoffs,
            last_recovery_attempt=head.authority.last_recovery_attempt,
        ),
        event_kind=EVENT_SUPERSESSION,
    )

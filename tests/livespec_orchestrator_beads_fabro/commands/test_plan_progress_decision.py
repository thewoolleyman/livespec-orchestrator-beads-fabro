"""What one sanctioned pointer write may do to the obligation, decided purely.

PURE, so every arm is a direct call. The four arms `contracts.md` section
"Required result, budget and progress epoch" names — no prior obligation, a
satisfied result, an unsatisfied one and an unobservable one — are each asserted
with a candidate that ASKS FOR A LATER DEADLINE AND A LARGER CEILING. That is
what separates "preserved the original" from "stored what it was handed": a
fixture asking for the original values cannot tell the two apart.

The SATISFIED and UNOBSERVABLE arms are asserted as a contrasting PAIR rather
than separately, because they are the two that look alike and must not behave
alike. Satisfaction is the one arm permitted to replace the budget; an
unobservable result is a failure to MEASURE, and letting it advance would make a
broken reader the cheapest route to a fresh deadline.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.commands._plan_progress_decision import (
    decide_tracked_write,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_outcome import (
    EVENT_HANDOFF,
    EVENT_PICKER,
    EVENT_POINTER,
    TrackedDecision,
    TrackedRefusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    ResultObservation,
    satisfied,
    unobservable,
    unsatisfied,
)
from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
    CAUSE_MISDERIVED,
    CausalSupersession,
)

_EPIC_ID = "bd-ib-decisionepic"
_TOKEN = "chain-record-current"
_NOW = "2026-10-13T09:00:00Z"
_ORIGINAL_DEADLINE = "2026-10-20T09:00:00Z"
_LATER_DEADLINE = "2099-01-01T00:00:00Z"
_PRIOR_RESULT: dict[str, object] = {
    "repo": "repo",
    "item_status": {"item_id": "bd-ib-prior", "status": "done"},
}
_RENAMED_RESULT: dict[str, object] = {
    "repo": "repo",
    "item_status": {"item_id": "bd-ib-renamed", "status": "done"},
}


def _head(*, authority: AuthorityState | None = None) -> ChainHead:
    return ChainHead(
        current_token_id=_TOKEN,
        latest_closed_token_id=None,
        epoch=3,
        authority=AuthorityState() if authority is None else authority,
    )


def _prior_authority(*, consumed: int = 1) -> AuthorityState:
    return AuthorityState(
        required_result=_PRIOR_RESULT,
        original_deadline=_ORIGINAL_DEADLINE,
        max_handoffs=5,
        consumed_handoffs=consumed,
    )


def _candidate(
    *,
    required_result: object = None,
    kind: str = "impl",
    ref: str = "bd-ib-prior",
) -> NextAction:
    return NextAction(
        kind=kind,
        ref=ref,
        text="Keep going.",
        required_result=_PRIOR_RESULT if required_result is None else required_result,
        budget={"deadline": _LATER_DEADLINE, "max_handoffs": 99},
    )


def _observation(*, status: str) -> ResultObservation:
    if status == "satisfied":
        return satisfied(
            repo="repo",
            target="bd-ib-prior",
            source="ledger",
            now=_NOW,
            evidence="status=done",
            detail="met",
        )
    if status == "unobservable":
        return unobservable(
            repo="repo",
            target="bd-ib-prior",
            source="ledger",
            now=_NOW,
            detail="the tenant did not answer",
        )
    return unsatisfied(
        repo="repo",
        target="bd-ib-prior",
        source="ledger",
        now=_NOW,
        evidence="status=ready",
        detail="not met",
    )


def _decision(outcome: object) -> TrackedDecision:
    assert isinstance(outcome, TrackedDecision), outcome
    return outcome


def _refusal(outcome: object) -> TrackedRefusal:
    assert isinstance(outcome, TrackedRefusal), outcome
    return outcome


@pytest.mark.parametrize(
    ("write", "expected_kind", "expected_consumed"),
    [("handoff", EVENT_HANDOFF, 1), ("pointer", EVENT_POINTER, 0)],
)
def test_with_no_prior_obligation_the_candidate_budget_becomes_the_original(
    write: str,
    expected_kind: str,
    expected_consumed: int,
) -> None:
    """Nothing is being preserved yet, so the candidate's own budget is adopted."""
    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=write == "handoff",
            observation=None,
        )
    )

    assert decision.authority.original_deadline == _LATER_DEADLINE
    assert decision.authority.max_handoffs == 99
    assert decision.authority.consumed_handoffs == expected_consumed
    assert decision.event_kind == expected_kind


def test_a_satisfied_result_permits_advancing_to_a_new_result_and_budget() -> None:
    """ "Satisfied results permit advancing to a new result and budget"."""
    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=True,
            observation=_observation(status="satisfied"),
        )
    )

    assert decision.authority.required_result == _RENAMED_RESULT
    assert decision.authority.original_deadline == _LATER_DEADLINE
    assert decision.authority.consumed_handoffs == 1


def test_an_unobservable_result_preserves_the_original_budget_instead() -> None:
    """The contrast to the case above, on identical fixtures but one status.

    "Unobservable results MUST preserve the original budget and refuse any
    transition claiming completion."
    """
    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=True,
            observation=_observation(status="unobservable"),
        )
    )

    assert decision.authority.required_result == _PRIOR_RESULT
    assert decision.authority.original_deadline == _ORIGINAL_DEADLINE
    assert decision.authority.max_handoffs == 5
    assert decision.authority.consumed_handoffs == 2


@pytest.mark.parametrize(
    ("write", "expected_kind", "expected_consumed"),
    [("handoff", EVENT_HANDOFF, 2), ("pointer", EVENT_POINTER, 1)],
)
def test_an_unsatisfied_result_preserves_both_limits_and_counts_only_handoffs(
    write: str,
    expected_kind: str,
    expected_consumed: int,
) -> None:
    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=write == "handoff",
            observation=_observation(status="unsatisfied"),
        )
    )

    assert decision.authority.original_deadline == _ORIGINAL_DEADLINE
    assert decision.authority.max_handoffs == 5
    assert decision.authority.consumed_handoffs == expected_consumed
    assert decision.event_kind == expected_kind
    assert decision.action.required_result == _PRIOR_RESULT


def test_renaming_an_unmet_target_is_refused_rather_than_read_as_new_work() -> None:
    """The one rewrite that would otherwise look like legitimate advancement."""
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
        )
    )

    assert "cannot be renamed" in refusal.detail
    assert "causal supersession" in refusal.detail


def test_renaming_an_unobservable_target_is_refused_naming_the_measurement() -> None:
    """The remedy differs, so the refusal says the target was UNOBSERVABLE.

    A reader told only "cannot be renamed" would look for a supersession to
    author, when what is actually owed is a diagnosis of the broken reading.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unobservable"),
        )
    )

    assert "is unobservable" in refusal.detail


@pytest.mark.parametrize(
    ("kind", "ref"),
    [("human", "Decide the routing."), ("none", "")],
)
def test_a_picker_pointer_keeps_null_tracking_while_retaining_the_obligation(
    kind: str,
    ref: str,
) -> None:
    """ "changing to them MUST retain any unmet obligation in the progress history".

    The POINTER goes null and the AUTHORITY keeps the obligation. Clearing the
    authority is how an unmet result would be discharged by pointing elsewhere.
    """
    candidate = NextAction(kind=kind, ref=ref, text="Ask.", required_result=None, budget=None)

    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=candidate,
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
        )
    )

    assert decision.event_kind == EVENT_PICKER
    assert decision.action.required_result is None
    assert decision.action.budget is None
    assert decision.authority.required_result == _PRIOR_RESULT
    assert decision.authority.original_deadline == _ORIGINAL_DEADLINE


def test_a_picker_pointer_with_no_prior_obligation_records_no_obligation() -> None:
    """There is nothing to retain, so the authority tracks nothing."""
    candidate = NextAction(kind="none", ref="", text="Idle.", required_result=None, budget=None)

    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(),
            candidate=candidate,
            now=_NOW,
            is_handoff=False,
            observation=None,
        )
    )

    assert decision.authority == AuthorityState()
    assert decision.event_kind == EVENT_PICKER


def test_a_candidate_whose_budget_is_unusable_is_refused_before_any_decision() -> None:
    candidate = NextAction(
        kind="impl",
        ref="bd-ib-prior",
        text="Keep going.",
        required_result=_PRIOR_RESULT,
        budget={"deadline": _LATER_DEADLINE},
    )

    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(),
            candidate=candidate,
            now=_NOW,
            is_handoff=False,
            observation=None,
        )
    )

    assert "deadline and positive max_handoffs" in refusal.detail


def test_a_candidate_whose_required_result_is_not_a_reference_is_refused() -> None:
    """Reached while continuing, where the identity comparison needs both sides."""
    candidate = NextAction(
        kind="impl",
        ref="bd-ib-prior",
        text="Keep going.",
        required_result={"repo": "repo", "shell": "test -f a.md"},
        budget={"deadline": _LATER_DEADLINE, "max_handoffs": 99},
    )

    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=candidate,
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
        )
    )

    assert "not a typed reference" in refusal.detail


def test_an_unreadable_prior_obligation_is_reconciled_rather_than_continued() -> None:
    """A prior result nobody can parse cannot be compared against, so continuing
    would preserve a budget whose target is unknown — a gauge passing blinded.
    """
    authority = AuthorityState(
        required_result={"repo": "repo", "shell": "test -f a.md"},
        original_deadline=_ORIGINAL_DEADLINE,
        max_handoffs=5,
        consumed_handoffs=1,
    )

    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=authority),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
        )
    )

    assert "unreadable" in refusal.detail
    assert "reconcile" in refusal.detail


def test_a_prior_obligation_with_no_observation_advances_rather_than_guessing() -> None:
    """The defensive arm, reachable only by calling this pure function directly.

    `_plan_tracked_write` reads the prior target whenever a prior obligation
    exists, so it never hands this combination in. Asserted so the arm has a
    stated meaning rather than being whatever falls out: with no reading of the
    prior target there is no evidence it is unmet, and preserving a budget on no
    evidence is the one thing worse than advancing on none.
    """
    decision = _decision(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=None,
        )
    )

    assert decision.authority.required_result == _RENAMED_RESULT


def _recovery() -> CausalRecovery:
    """A WELL-FORMED attempt, so each case below refuses for its own reason.

    A malformed attempt would be refused by the validator regardless, which
    would make these two cases pass without the not-expired guards existing.
    """
    return CausalRecovery(
        required_result=_PRIOR_RESULT,
        previous_epoch=3,
        failure_evidence="the provider returned usageLimitExceeded",
        cause="host",
        next_operation="impl:bd-ib-prior",
        attempt_id="attempt-0001",
        attempt_deadline="2026-10-20T12:00:00Z",
    )


def test_recovery_against_an_epic_with_no_obligation_at_all_is_refused() -> None:
    """There is nothing expired, so there is nothing to recover.

    Admitting one would let a session bank attempts before any obligation
    exists and spend them against whatever obligation arrived later.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=False,
            observation=None,
            recovery=_recovery(),
        )
    )

    assert "not expired" in refusal.detail


def test_recovery_against_a_satisfied_obligation_is_refused() -> None:
    """A met obligation advances on its own; it does not recover."""
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="satisfied"),
            recovery=_recovery(),
        )
    )

    assert "not expired" in refusal.detail


def _supersession() -> CausalSupersession:
    """One well-formed supersession naming the prior obligation at its epoch.

    Every case below refuses BEFORE the cause's own evidence is read, so the
    claim's shape only has to be well-formed: what the cases discriminate is
    which obligation state a supersession may be carried against at all.
    """
    return CausalSupersession(
        superseded_result_identity="repo item_status bd-ib-prior status done",
        previous_epoch=3,
        cause=CAUSE_MISDERIVED,
        deriving_operation_id="op-derived",
        open_carrier_id="cr-open",
        writer="plan-session",
    )


def test_a_write_carrying_both_a_recovery_and_a_supersession_is_refused() -> None:
    """The two answer different questions about one obligation.

    A recovery reopens an expired obligation and a supersession replaces an
    unmet one, so a write claiming both would have one of them graded and the
    other silently dropped — and the write would report success either way.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
            recovery=_recovery(),
            supersession=_supersession(),
        )
    )

    assert "never both" in refusal.detail


def test_a_supersession_against_an_epic_with_no_obligation_is_refused() -> None:
    """There is nothing standing that could be replaced.

    Admitting one would let a write bank a rename before any obligation exists
    and have it apply to whatever obligation arrived next.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=None,
            supersession=_supersession(),
        )
    )

    assert "no obligation stands" in refusal.detail


def test_a_supersession_against_a_satisfied_obligation_is_refused() -> None:
    """A satisfied result already permits a new result AND a new budget.

    This is the one state in which a supersession could carry a budget of the
    caller's own choosing, because the satisfied arm is the arm that replaces
    one — so the claim is refused rather than merged into it.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority()),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="satisfied"),
            supersession=_supersession(),
        )
    )

    assert "already permits" in refusal.detail


def test_a_supersession_of_an_expired_obligation_remains_subject_to_expiry() -> None:
    """A supersession does not reopen an obligation that has run out.

    The clause says so in as many words, and it is the one route that would
    otherwise turn an exhausted budget into a fresh one: a rename is admitted
    only while the obligation it renames still has budget left.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(authority=_prior_authority(consumed=5)),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
            supersession=_supersession(),
        )
    )

    assert "does not reopen it" in refusal.detail


def test_a_supersession_of_an_unreadable_prior_obligation_is_reconciled_first() -> None:
    """An obligation nobody can parse names no identity to supersede.

    Its own control is the expired case above, which reaches the same write with
    a READABLE obligation and reports the other refusal: a build that had
    stopped parsing the prior obligation would answer this one for both.
    """
    refusal = _refusal(
        decide_tracked_write(
            epic_id=_EPIC_ID,
            head=_head(
                authority=AuthorityState(
                    required_result={"shell": "test -f done"},
                    original_deadline=_LATER_DEADLINE,
                    max_handoffs=5,
                    consumed_handoffs=1,
                )
            ),
            candidate=_candidate(required_result=_RENAMED_RESULT),
            now=_NOW,
            is_handoff=False,
            observation=_observation(status="unsatisfied"),
            supersession=_supersession(),
        )
    )

    assert "unreadable" in refusal.detail

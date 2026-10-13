"""The durable obligation read out of an authority state, and its exact limits.

PURE, so every case here is a direct call with no store and no double. The
boundaries are the point: `contracts.md` section "Required result, budget and
progress epoch" says "At the exact deadline or when accepted handoffs reach
max_handoffs, the next continuation is expired", so each limit is asserted ONE
STEP SHORT, EXACTLY AT, and ONE STEP PAST its boundary. A test that only probed
"well past" would pass against a `>` comparison, which is the off-by-one that
grants one extra handoff and one extra moment of deadline to every obligation in
the fleet.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    EXPIRY_DEADLINE,
    EXPIRY_HANDOFFS,
    CandidateBudget,
    Obligation,
    budget_projection,
    candidate_budget,
    obligation_expiry,
    obligation_of,
    projected_action,
)

_DEADLINE = "2026-10-20T09:00:00Z"
_RESULT: dict[str, object] = {
    "repo": "repo",
    "item_status": {"item_id": "bd-ib-target", "status": "done"},
}


def _obligation(*, consumed: int = 0, maximum: int = 5) -> Obligation:
    return Obligation(
        required_result=_RESULT,
        original_deadline=_DEADLINE,
        max_handoffs=maximum,
        consumed_handoffs=consumed,
    )


def test_an_authority_carrying_both_limits_reads_as_an_obligation() -> None:
    obligation = obligation_of(
        authority=AuthorityState(
            required_result=_RESULT,
            original_deadline=_DEADLINE,
            max_handoffs=5,
            consumed_handoffs=2,
        )
    )

    assert obligation == _obligation(consumed=2)


@pytest.mark.parametrize(
    ("deadline", "maximum"),
    [
        (None, 5),
        (_DEADLINE, None),
        (None, None),
    ],
)
def test_a_half_recorded_budget_reads_as_no_obligation_at_all(
    deadline: str | None,
    maximum: int | None,
) -> None:
    """An obligation missing either limit could never expire.

    Admitting one would create a budget that silently never runs out, which at
    every surface reads exactly like a budget being honoured.
    """
    assert (
        obligation_of(
            authority=AuthorityState(
                required_result=_RESULT,
                original_deadline=deadline,
                max_handoffs=maximum,
            )
        )
        is None
    )


@pytest.mark.parametrize(
    ("consumed", "expected"),
    [
        (3, None),
        (4, EXPIRY_HANDOFFS),
        (5, EXPIRY_HANDOFFS),
    ],
)
def test_the_handoff_ceiling_is_inclusive(consumed: int, expected: str | None) -> None:
    """`reach max_handoffs` means equality expires, so 4 of 4 is spent."""
    assert (
        obligation_expiry(
            obligation=_obligation(consumed=consumed, maximum=4),
            now="2026-10-13T09:00:00Z",
        )
        == expected
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-10-20T08:59:59Z", None),
        ("2026-10-20T09:00:00Z", EXPIRY_DEADLINE),
        ("2026-10-20T09:00:01Z", EXPIRY_DEADLINE),
    ],
)
def test_the_deadline_is_inclusive_to_the_exact_second(now: str, expected: str | None) -> None:
    """ "At the exact deadline ... the next continuation is expired"."""
    assert obligation_expiry(obligation=_obligation(), now=now) == expected


def test_an_unreadable_deadline_expires_rather_than_holding() -> None:
    """A budget gate fails CLOSED: an instant nobody can read is not headroom."""
    obligation = Obligation(
        required_result=_RESULT,
        original_deadline="not-an-instant",
        max_handoffs=5,
        consumed_handoffs=0,
    )

    assert obligation_expiry(obligation=obligation, now="2026-10-13T09:00:00Z") == EXPIRY_DEADLINE


def test_the_count_is_reported_ahead_of_a_clock_that_also_passed() -> None:
    """Both limits reached reports the COUNT, which is the settled fact.

    The ceiling is a fact about work already accepted; the clock keeps moving.
    Naming the count tells a reader which limit actually stopped the work.
    """
    assert (
        obligation_expiry(obligation=_obligation(consumed=5), now="2099-01-01T00:00:00Z")
        == EXPIRY_HANDOFFS
    )


@pytest.mark.parametrize(
    "budget",
    [
        "not-an-object",
        None,
        {"max_handoffs": 5},
        {"deadline": 17, "max_handoffs": 5},
        {"deadline": _DEADLINE},
        {"deadline": _DEADLINE, "max_handoffs": "five"},
        {"deadline": _DEADLINE, "max_handoffs": True},
        {"deadline": _DEADLINE, "max_handoffs": 0},
        {"deadline": _DEADLINE, "max_handoffs": -1},
    ],
)
def test_an_unusable_candidate_budget_reads_as_none(budget: object) -> None:
    """`True` is excluded explicitly, because it is an `int` in Python."""
    assert candidate_budget(budget=budget) is None


def test_a_well_formed_candidate_budget_reads_as_its_two_limits() -> None:
    assert candidate_budget(budget={"deadline": _DEADLINE, "max_handoffs": 5}) == CandidateBudget(
        deadline=_DEADLINE, max_handoffs=5
    )


def test_a_candidate_budget_ignores_the_progress_fields_a_writer_cannot_set() -> None:
    """`handoff_count` and `epoch` are PROJECTED, never accepted.

    A writer handing itself a lower count must not get one, so the reader takes
    only the two ratified limits and drops the rest on the floor.
    """
    assert candidate_budget(
        budget={
            "deadline": _DEADLINE,
            "max_handoffs": 5,
            "handoff_count": 0,
            "epoch": "99",
        }
    ) == CandidateBudget(deadline=_DEADLINE, max_handoffs=5)


def test_the_projection_renders_both_limits_the_count_and_the_epoch() -> None:
    assert budget_projection(obligation=_obligation(consumed=2), epoch=7) == {
        "deadline": _DEADLINE,
        "max_handoffs": 5,
        "handoff_count": 2,
        "epoch": "7",
    }


def test_an_authority_tracking_nothing_leaves_a_picker_pointer_untouched() -> None:
    """A `human` pointer's explicit null tracking fields must stay null.

    The clause requires both to be null for that kind, so projecting an
    obligation onto one would make the pointer itself invalid.
    """
    action = NextAction(
        kind="human", ref="decide", text="Decide.", required_result=None, budget=None
    )

    assert projected_action(action=action, authority=AuthorityState(), epoch=3) is action


def test_a_tracked_pointer_against_an_untracked_authority_is_left_alone() -> None:
    """The SECOND of the projection's two hand-back guards.

    Its sibling above keys on the ACTION carrying null tracking; this one keys
    on the AUTHORITY tracking no obligation. Both are needed and they fire on
    different inputs, so each needs its own case: a tracked pointer committed
    against an empty authority has nothing to project, and inventing a budget
    for it is exactly what "legacy reads alone MUST NOT invent budgets" forbids
    one level up.
    """
    action = NextAction(
        kind="impl",
        ref="bd-ib-target",
        text="Keep going.",
        required_result=_RESULT,
        budget={"deadline": _DEADLINE, "max_handoffs": 5},
    )

    assert projected_action(action=action, authority=AuthorityState(), epoch=3) is action


def test_the_projection_overwrites_whatever_budget_the_candidate_proposed() -> None:
    """This is the assertion the whole module exists for.

    The candidate asks for a 2099 deadline and a ceiling of 99; the committed
    authority says otherwise, and the authority is what lands.
    """
    action = NextAction(
        kind="impl",
        ref="bd-ib-target",
        text="Keep going.",
        required_result={"repo": "repo", "item_status": {"item_id": "other", "status": "done"}},
        budget={"deadline": "2099-01-01T00:00:00Z", "max_handoffs": 99},
    )

    projected = projected_action(
        action=action,
        authority=AuthorityState(
            required_result=_RESULT,
            original_deadline=_DEADLINE,
            max_handoffs=5,
            consumed_handoffs=1,
        ),
        epoch=4,
    )

    assert projected.required_result == _RESULT
    assert projected.budget == {
        "deadline": _DEADLINE,
        "max_handoffs": 5,
        "handoff_count": 1,
        "epoch": "4",
    }
    assert (projected.kind, projected.ref, projected.text) == (action.kind, action.ref, action.text)


@given(
    consumed=st.integers(min_value=0, max_value=50),
    maximum=st.integers(min_value=1, max_value=50),
)
def test_expiry_by_count_is_exactly_the_at_or_over_relation(consumed: int, maximum: int) -> None:
    """The property the two boundary cases above sample from."""
    expiry = obligation_expiry(
        obligation=_obligation(consumed=consumed, maximum=maximum),
        now="2026-10-13T09:00:00Z",
    )

    assert (expiry == EXPIRY_HANDOFFS) == (consumed >= maximum)


@given(maximum=st.integers(min_value=1, max_value=50), epoch=st.integers(min_value=0))
def test_a_projection_always_round_trips_through_the_candidate_reader(
    maximum: int,
    epoch: int,
) -> None:
    """A projected budget is itself a readable candidate budget.

    Without this the pointer could carry a budget the next write's own reader
    rejects, which would refuse every continuation of a perfectly sound
    obligation.
    """
    obligation = _obligation(maximum=maximum)

    projected = budget_projection(obligation=obligation, epoch=epoch)

    assert candidate_budget(budget=projected) == CandidateBudget(
        deadline=obligation.original_deadline, max_handoffs=maximum
    )

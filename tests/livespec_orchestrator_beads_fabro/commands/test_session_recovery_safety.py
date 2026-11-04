"""A real safety barrier defers mutation; an idle session is not one.

Scenario 164 of `SPECIFICATION/scenarios.md` lists the three real barriers —
"human HOLD with authority, reason, owner and release condition", a "running
commit hook" and an "open Red-Green pair" — and refuses the imitations: "an idle
session, unanswered notification, prose deadline or stale completed diagnostic
... alone do not create a HOLD".
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._session_recovery_safety import (
    BARRIER_COMMIT_HOOK,
    BARRIER_HUMAN_HOLD,
    BARRIER_RED_GREEN_PAIR,
    DIAGNOSTIC_HOLD_INCOMPLETE,
    DIAGNOSTIC_NO_BARRIER_FROM_IDLE_FACTS,
    MUTATION_DEFERRED,
    MUTATION_PERMITTED,
    SAFETY_BARRIERS,
    HumanHold,
    SafetyState,
    safety_verdict,
)

_HOLD = HumanHold(
    authority="maintainer",
    reason="the merge queue is paused for the storage move",
    owner="thewoolleyman",
    release_condition="the storage move completes and master is green",
)


def _state(
    *,
    hold: HumanHold | None = None,
    commit_hook_running: bool = False,
    red_green_pair_open: bool = False,
    session_idle: bool = False,
    notification_unanswered: bool = False,
    prose_deadline: str | None = None,
    stale_diagnostic: str | None = None,
) -> SafetyState:
    return SafetyState(
        hold=hold,
        commit_hook_running=commit_hook_running,
        red_green_pair_open=red_green_pair_open,
        session_idle=session_idle,
        notification_unanswered=notification_unanswered,
        prose_deadline=prose_deadline,
        stale_diagnostic=stale_diagnostic,
    )


def test_a_valid_human_hold_defers_mutation_and_names_its_authority() -> None:
    deferred = safety_verdict(state=_state(hold=_HOLD))

    assert deferred.state == MUTATION_DEFERRED
    assert not deferred.mutation_permitted
    assert deferred.barrier == BARRIER_HUMAN_HOLD
    assert deferred.hold == _HOLD
    assert deferred.hold is not None
    assert deferred.hold.release_condition == "the storage move completes and master is green"


@pytest.mark.parametrize(
    ("state", "barrier"),
    [
        (_state(commit_hook_running=True), BARRIER_COMMIT_HOOK),
        (_state(red_green_pair_open=True), BARRIER_RED_GREEN_PAIR),
    ],
)
def test_an_active_commit_and_an_open_red_green_pair_are_visible_barriers(
    *, state: SafetyState, barrier: str
) -> None:
    deferred = safety_verdict(state=state)

    assert deferred.state == MUTATION_DEFERRED
    assert deferred.barrier == barrier
    assert deferred.hold is None


def test_a_hold_missing_any_of_its_four_fields_is_not_a_hold() -> None:
    incomplete = safety_verdict(
        state=_state(
            hold=HumanHold(
                authority="maintainer",
                reason="  ",
                owner="thewoolleyman",
                release_condition="master is green",
            )
        )
    )

    assert incomplete.state == MUTATION_PERMITTED
    assert incomplete.mutation_permitted
    assert incomplete.barrier is None
    assert DIAGNOSTIC_HOLD_INCOMPLETE in incomplete.diagnostics


def test_idle_facts_alone_permit_mutation_and_are_reported_rather_than_obeyed() -> None:
    permitted = safety_verdict(
        state=_state(
            session_idle=True,
            notification_unanswered=True,
            prose_deadline="we should be done by 14:25",
            stale_diagnostic="diagnose-plan-progress:bd-ib-jnpvh4",
        )
    )

    assert permitted.state == MUTATION_PERMITTED
    assert permitted.barrier is None
    assert DIAGNOSTIC_NO_BARRIER_FROM_IDLE_FACTS in permitted.diagnostics


def test_a_quiet_host_with_no_facts_at_all_permits_mutation_with_no_diagnostics() -> None:
    permitted = safety_verdict(state=_state())

    assert permitted.state == MUTATION_PERMITTED
    assert permitted.barrier is None
    assert permitted.diagnostics == ()


def test_a_hold_outranks_the_other_two_barriers_so_its_authority_is_reported() -> None:
    """A deferral must name the barrier whose release condition a reader can act on."""
    deferred = safety_verdict(
        state=_state(hold=_HOLD, commit_hook_running=True, red_green_pair_open=True)
    )

    assert deferred.barrier == BARRIER_HUMAN_HOLD
    assert deferred.hold == _HOLD


def test_the_barrier_vocabulary_is_closed_and_holds_exactly_the_three_real_ones() -> None:
    assert SAFETY_BARRIERS == (
        BARRIER_HUMAN_HOLD,
        BARRIER_COMMIT_HOOK,
        BARRIER_RED_GREEN_PAIR,
    )
    assert "idle" not in SAFETY_BARRIERS
    assert "unanswered-notification" not in SAFETY_BARRIERS

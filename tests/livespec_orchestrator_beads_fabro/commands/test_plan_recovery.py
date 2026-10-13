"""Typed causal recovery, decided purely, at the arms the journey cannot reach.

`tests/integration/test_plan_causal_recovery_scenario147.py` binds the scenario
end to end through the public writers. This module covers the grammar and the
authorization table directly, which is where the two measured defects lived.

THE GRAMMAR IS ASSERTED IN BOTH DIRECTIONS and that is the whole point. A
validator that refused every operation would satisfy every negative case ever
written for it, so each refused spelling sits beside the accepted spelling it is
one character away from — `impl:` with a real id against `impl:` with none,
`diagnose-plan-progress:` against `diagnose-` plus anything else, a real spec
operation against an invented one.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
from livespec_orchestrator_beads_fabro.commands._plan_recovery import (
    CAUSE_HOST,
    CAUSE_ITEM,
    CAUSE_UNKNOWN,
    CausalRecovery,
    RecoveryRefusal,
    authorized_recovery_operation,
    is_executable_operation,
    item_attributable_attempts,
    recovery_record,
    validate_causal_recovery,
)

_EPIC_ID = "bd-ib-recoveryepic"
_TARGET_ID = "bd-ib-recoverytarget"
_NOW = "2026-10-15T09:00:00Z"
_ATTEMPT_DEADLINE = "2026-10-15T12:00:00Z"
_RESULT: dict[str, object] = {
    "repo": "repo",
    "item_status": {"item_id": _TARGET_ID, "status": "done"},
}
_IDENTITY = f"repo item_status {_TARGET_ID} status done"


def _action(*, kind: str = "impl", ref: str = _TARGET_ID) -> NextAction:
    return NextAction(
        kind=kind,
        ref=ref,
        text="Keep going.",
        required_result=_RESULT,
        budget={"deadline": "2026-10-14T09:00:00Z", "max_handoffs": 5},
    )


def _recovery(
    *,
    cause: str = CAUSE_HOST,
    next_operation: str | None = None,
    **overrides: object,
) -> CausalRecovery:
    fields: dict[str, object] = {
        "required_result": _RESULT,
        "previous_epoch": 1,
        "failure_evidence": "the provider returned usageLimitExceeded",
        "cause": cause,
        "next_operation": f"impl:{_TARGET_ID}" if next_operation is None else next_operation,
        "attempt_id": "attempt-0001",
        "attempt_deadline": _ATTEMPT_DEADLINE,
    }
    fields.update(overrides)
    return CausalRecovery(**fields)  # pyright: ignore[reportArgumentType]


def _validate(*, recovery: CausalRecovery, action: NextAction | None = None) -> object:
    return validate_causal_recovery(
        recovery=recovery,
        action=_action() if action is None else action,
        epic_id=_EPIC_ID,
        current_epoch=1,
        current_result_identity=_IDENTITY,
        now=_NOW,
    )


def test_the_identity_the_fixtures_assume_is_the_identity_the_reference_renders() -> None:
    """A positive control on the fixture itself.

    Every case below compares against `_IDENTITY`. Were that string wrong, the
    obligation-naming arm would refuse everything and each later case would be
    passing for the wrong reason.
    """
    assert _validate(recovery=_recovery()) is None


@pytest.mark.parametrize(
    "operation",
    [
        f"impl:{_TARGET_ID}",
        "impl:bd-ib-abc123.4",
        f"diagnose-plan-progress:{_EPIC_ID}",
        "propose-change:relay-delivery",
        "revise:relay-delivery",
        "critique:relay-delivery",
        "prune-history:relay-delivery",
    ],
)
def test_every_operation_with_a_real_executor_is_in_the_grammar(operation: str) -> None:
    """`impl:` and the diagnosis run through drive; the four spec operations
    run through the Livespec Driver."""
    assert is_executable_operation(operation=operation) is True


@pytest.mark.parametrize(
    "operation",
    [
        "",
        "I will try a different approach.",
        "diagnose-this-is-not-a-supported-operation",
        "diagnose-plan-progress:",
        "impl:",
        "impl:Not-An-Id",
        "deploy:relay-delivery",
        "revise:",
        "revise:Relay-Delivery",
        f"impl:{_TARGET_ID} && rm -rf /",
        f"  impl:{_TARGET_ID}",
        "acknowledged",
    ],
)
def test_nothing_outside_the_closed_grammar_is_executable(operation: str) -> None:
    """The two measured defects are the second and third entries here.

    A `diagnose-` prefix is a SHAPE that resembles an operation, which is
    exactly why it was accepted; a prose sentence names no operation at all.
    The trailing-shell entry matters because the grammar is matched with
    `fullmatch`, so a prefix match would admit an appended command.
    """
    assert is_executable_operation(operation=operation) is False


@pytest.mark.parametrize(
    ("cause", "kind", "ref", "expected"),
    [
        (CAUSE_UNKNOWN, "impl", _TARGET_ID, f"diagnose-plan-progress:{_EPIC_ID}"),
        (CAUSE_UNKNOWN, "spec-op", "revise:relay", f"diagnose-plan-progress:{_EPIC_ID}"),
        (CAUSE_HOST, "impl", _TARGET_ID, f"impl:{_TARGET_ID}"),
        (CAUSE_ITEM, "impl", _TARGET_ID, f"impl:{_TARGET_ID}"),
        (CAUSE_HOST, "spec-op", "revise:relay", "revise:relay"),
    ],
)
def test_the_cause_decides_which_operation_is_authorized(
    cause: str,
    kind: str,
    ref: str,
    expected: str,
) -> None:
    """ "Unknown causes require diagnosis and known host causes require bounded
    host recovery" — so the caller does not choose."""
    assert (
        authorized_recovery_operation(
            action=_action(kind=kind, ref=ref),
            epic_id=_EPIC_ID,
            cause=cause,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("cause", "kind", "ref"),
    [
        ("vibes", "impl", _TARGET_ID),
        (CAUSE_HOST, "spec-op", "I will try a different approach."),
        (CAUSE_HOST, "impl", "   "),
        (CAUSE_HOST, "human", "Decide."),
        (CAUSE_HOST, "impl", "Not-An-Id"),
    ],
)
def test_an_unusable_pointer_or_cause_authorizes_nothing(
    cause: str,
    kind: str,
    ref: str,
) -> None:
    """The derived operation is itself grammar-checked.

    This is the half the draft validator skipped: a pointer whose `ref` is
    prose derives a prose "operation", and an equality test against it passes.
    """
    assert (
        authorized_recovery_operation(
            action=_action(kind=kind, ref=ref),
            epic_id=_EPIC_ID,
            cause=cause,
        )
        is None
    )


def test_an_attempt_naming_a_different_obligation_is_refused() -> None:
    other: dict[str, object] = {
        "repo": "repo",
        "item_status": {"item_id": "bd-ib-other", "status": "done"},
    }

    refusal = _validate(recovery=_recovery(required_result=other))

    assert isinstance(refusal, RecoveryRefusal)
    assert _IDENTITY in refusal.detail


def test_an_attempt_whose_obligation_is_unparseable_is_refused() -> None:
    """A shell predicate is not a reference, so it names no obligation."""
    refusal = _validate(recovery=_recovery(required_result={"repo": "r", "shell": "true"}))

    assert isinstance(refusal, RecoveryRefusal)


def test_an_authorized_operation_for_a_cause_with_no_authority_is_refused() -> None:
    """The arm where the GRAMMAR passes but no operation is authorized.

    The operation is a real spec operation, so the first gate admits it; the
    pointer is `human`, which authorizes no operation at all.
    """
    refusal = _validate(
        recovery=_recovery(next_operation="revise:relay-delivery"),
        action=_action(kind="human", ref="Decide."),
    )

    assert isinstance(refusal, RecoveryRefusal)
    assert "no executable operation is authorized" in refusal.detail


def test_a_grammatical_operation_the_cause_does_not_authorize_is_refused() -> None:
    """Both gates pass individually; equality is what refuses.

    `revise:relay-delivery` is executable and the host cause authorizes a real
    operation — just not this one.
    """
    refusal = _validate(recovery=_recovery(next_operation="revise:relay-delivery"))

    assert isinstance(refusal, RecoveryRefusal)
    assert "authorizes only" in refusal.detail


def test_an_empty_attempt_id_is_refused() -> None:
    refusal = _validate(recovery=_recovery(attempt_id="   "))

    assert isinstance(refusal, RecoveryRefusal)
    assert "attempt id" in refusal.detail


@pytest.mark.parametrize(
    "receipts",
    [
        {"claim_receipt": "claimed"},
        {"execution_receipt": "ran"},
        {"outcome_receipt": "worked"},
    ],
)
def test_each_receipt_on_a_fresh_attempt_is_refused_on_its_own(
    receipts: dict[str, object],
) -> None:
    """All three are asserted separately because each is a distinct claim.

    A validator checking only one would admit an attempt asserting either of
    the others, and "Claim, execution and outcome receipts MUST remain
    distinct" is about all three.
    """
    refusal = _validate(recovery=_recovery(**receipts))

    assert isinstance(refusal, RecoveryRefusal)
    assert "receipt" in refusal.detail


def test_an_attempt_deadline_exactly_at_now_bounds_nothing() -> None:
    """The boundary is INCLUSIVE, matching every other deadline in this tree."""
    refusal = _validate(recovery=_recovery(attempt_deadline=_NOW))

    assert isinstance(refusal, RecoveryRefusal)
    assert "bounds nothing" in refusal.detail


def test_an_item_cause_increments_the_repetition_count() -> None:
    record = recovery_record(
        recovery=_recovery(cause=CAUSE_ITEM),
        prior=AuthorityState(),
        now=_NOW,
    )

    assert record["item_attributable_attempts"] == 1
    assert record["attempt"]["cause"] == CAUSE_ITEM
    assert record["attempt"]["recorded_at"] == _NOW
    assert record["attempt"]["execution_receipt"] is None


@pytest.mark.parametrize("cause", [CAUSE_HOST, CAUSE_UNKNOWN])
def test_a_host_or_unknown_cause_carries_the_count_forward_unchanged(cause: str) -> None:
    """ "neither increments or resets the item-attributable repetition count"."""
    prior = AuthorityState(last_recovery_attempt={"attempt": {}, "item_attributable_attempts": 3})

    record = recovery_record(recovery=_recovery(cause=cause), prior=prior, now=_NOW)

    assert record["item_attributable_attempts"] == 3


@pytest.mark.parametrize(
    "stored",
    [
        None,
        "not-a-record",
        {},
        {"item_attributable_attempts": "three"},
        {"item_attributable_attempts": True},
        {"item_attributable_attempts": -1},
    ],
)
def test_an_unreadable_recovery_record_counts_as_no_item_attempts(stored: object) -> None:
    """Zero rather than an invented number.

    The count exists to BOUND re-dispatch of a failing item, so inventing a
    nonzero one from a record nobody could read would park work on evidence
    nobody could read either.
    """
    assert item_attributable_attempts(authority=AuthorityState(last_recovery_attempt=stored)) == 0


def test_a_readable_count_is_returned_as_stored() -> None:
    assert (
        item_attributable_attempts(
            authority=AuthorityState(
                last_recovery_attempt={"attempt": {}, "item_attributable_attempts": 2}
            )
        )
        == 2
    )

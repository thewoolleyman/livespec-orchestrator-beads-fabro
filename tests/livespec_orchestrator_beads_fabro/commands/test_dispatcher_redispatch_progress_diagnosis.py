"""A diagnosis is cleared only by one fresh typed recovery; the count follows the latest history."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchRecovery,
    redispatch_progress_decision,
)


def _attempt(
    run_id: str,
    *,
    order: int = 0,
    attributable: bool | None = True,
    diagnosed: bool = False,
    workflow: str = "w",
) -> CompletedAttempt:
    return CompletedAttempt(
        run_id=run_id,
        terminal_cause=f"{run_id} failed",
        high_water_milestone="implement",
        high_water_order=order,
        item_attributable=attributable,
        workflow_identity=workflow,
        diagnosed=diagnosed,
    )


def _recovery(
    prior: tuple[str, ...], *, attempt_id: str = "rec", diagnosis: str = "measured"
) -> RedispatchRecovery:
    return RedispatchRecovery(
        attempt_id=attempt_id,
        prior_run_ids=prior,
        diagnosis=diagnosis,
        operation="dispatch",
        execution_evidence="receipt",
    )


def test_a_diagnosis_names_its_run_and_one_matching_recovery_clears_it() -> None:
    """An unknown cause refuses; a recovery over the whole history authorizes once."""
    attempts = (_attempt("r1"), _attempt("r2", attributable=None))
    plain = redispatch_progress_decision(limit=2, attempts=attempts)
    assert plain.diagnosis == "r2 has an unknown terminal cause"
    assert plain.diagnosis_run_id == "r2"

    cleared = redispatch_progress_decision(
        limit=2, attempts=attempts, recovery=_recovery(("r1", "r2"))
    )
    assert cleared.diagnosis is None
    assert cleared.authorized_recovery_attempt_id == "rec"


def test_a_diagnosis_recovery_must_be_complete_causal_and_unspent() -> None:
    """Missing fields, the wrong history and a spent id each keep the diagnosis."""
    attempts = (_attempt("r1", attributable=None),)
    blank = redispatch_progress_decision(
        limit=2, attempts=attempts, recovery=_recovery(("r1",), diagnosis="")
    )
    wrong = redispatch_progress_decision(limit=2, attempts=attempts, recovery=_recovery(("other",)))
    spent = redispatch_progress_decision(
        limit=2,
        attempts=attempts,
        recovery=_recovery(("r1",)),
        consumed_recovery_attempt_ids=frozenset({"rec"}),
    )
    assert blank.diagnosis == "causal recovery requires measured diagnosis"
    assert wrong.diagnosis == "causal recovery must name the diagnosed run history"
    assert spent.diagnosis == "r1 has an unknown terminal cause"
    assert {
        blank.authorized_recovery_attempt_id,
        wrong.authorized_recovery_attempt_id,
        spent.authorized_recovery_attempt_id,
    } == {None}


def test_an_incomparable_workflow_is_diagnosed_with_the_same_exit() -> None:
    """A changed graph is a diagnosis too, and the recovery covers the history through it."""
    attempts = (_attempt("r1"), _attempt("r2", workflow="changed"))
    plain = redispatch_progress_decision(limit=2, attempts=attempts)
    assert plain.diagnosis_run_id == "r2"
    cleared = redispatch_progress_decision(
        limit=2, attempts=attempts, recovery=_recovery(("r1", "r2"))
    )
    assert cleared.authorized_recovery_attempt_id == "rec"


def test_a_diagnosed_attempt_is_the_explicit_new_baseline() -> None:
    """The diagnosed run resets the flat count and sets the mark later runs are held to."""
    attempts = (
        _attempt("r1"),
        _attempt("r2"),
        _attempt("r3", attributable=None, diagnosed=True, workflow="changed", order=3),
        _attempt("r4", workflow="changed", order=3),
    )
    decision = redispatch_progress_decision(limit=2, attempts=attempts)
    assert decision.refusal is None
    assert decision.diagnosis is None
    assert decision.non_progress_run_ids == ("r4",)


def test_the_refusal_follows_the_whole_flat_history_and_a_later_advance_clears_it() -> None:
    """A run after the limit is named too, so an old recovery cannot cover it; progress resets."""
    flat = (_attempt("base"), _attempt("a"), _attempt("b"), _attempt("c"))
    refused = redispatch_progress_decision(limit=2, attempts=flat)
    assert refused.refusal is not None
    assert refused.refusal.run_ids == ("a", "b", "c")
    stale = redispatch_progress_decision(limit=2, attempts=flat, recovery=_recovery(("a", "b")))
    assert stale.authorized_recovery_attempt_id is None
    assert stale.diagnosis == "causal recovery must name the refused non-progress run history"

    advanced = redispatch_progress_decision(limit=2, attempts=(*flat, _attempt("d", order=1)))
    assert advanced.refusal is None
    assert advanced.non_progress_run_ids == ()

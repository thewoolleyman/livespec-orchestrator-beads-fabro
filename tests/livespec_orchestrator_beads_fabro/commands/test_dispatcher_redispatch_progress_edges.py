"""Coverage for the non-refusal arms of across-dispatch progress."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    redispatch_progress_decision,
)


def test_progress_host_duplicates_and_active_runs_do_not_consume_the_limit() -> None:
    """Only a fresh, completed attributable terminal can make the count grow."""
    decision = redispatch_progress_decision(
        limit=2,
        attempts=(
            _attempt(run_id="base", milestone="implement"),
            _attempt(run_id="advance", milestone="review", order=1),
            _attempt(run_id="host", milestone="review", attributable=False),
            _attempt(run_id="active", milestone="review", completed=False),
            _attempt(run_id="advance", milestone="review", cause="duplicate"),
            _attempt(run_id="flat", milestone="review"),
        ),
    )
    assert decision.refusal is None
    assert decision.diagnosis is None
    assert decision.non_progress_run_ids == ("flat",)


def test_unknown_incomparable_and_invalid_policy_require_diagnosis() -> None:
    """Unsafe readings refuse diagnosis instead of making a count up."""
    invalid = redispatch_progress_decision(limit=None, attempts=())
    boolean = redispatch_progress_decision(limit=True, attempts=())
    zero = redispatch_progress_decision(limit=0, attempts=())
    unknown = redispatch_progress_decision(
        limit=1,
        attempts=(_attempt(run_id="unknown", milestone="implement", attributable=None),),
    )
    incomparable = redispatch_progress_decision(
        limit=1,
        attempts=(
            _attempt(run_id="one", milestone="implement", workflow="first"),
            _attempt(run_id="two", milestone="implement", workflow="second"),
        ),
    )
    assert invalid.diagnosis == "dispatcher.redispatch_no_progress_limit must be a positive integer"
    assert boolean.diagnosis == invalid.diagnosis
    assert zero.diagnosis == invalid.diagnosis
    assert unknown.diagnosis == "unknown has an unknown terminal cause"
    assert incomparable.diagnosis == "two uses incomparable workflow second"


def _attempt(
    *,
    run_id: str,
    milestone: str,
    order: int = 0,
    cause: str = "failed",
    attributable: bool | None = True,
    workflow: str = "default",
    completed: bool = True,
) -> CompletedAttempt:
    return CompletedAttempt(
        run_id=run_id,
        terminal_cause=cause,
        high_water_milestone=milestone,
        high_water_order=order,
        item_attributable=attributable,
        workflow_identity=workflow,
        completed=completed,
    )

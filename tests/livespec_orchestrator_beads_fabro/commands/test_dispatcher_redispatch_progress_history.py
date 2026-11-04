"""The whole attempt history decides, so later progress and failures both count."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchRecovery,
    redispatch_progress_decision,
)


def _attempt(*, run_id: str, order: int = 0, milestone: str = "implement") -> CompletedAttempt:
    return CompletedAttempt(
        run_id=run_id,
        terminal_cause="failed",
        high_water_milestone=milestone,
        high_water_order=order,
        item_attributable=True,
    )


def test_progress_after_the_limit_was_reached_resets_the_count() -> None:
    """A later attempt that advances the mark releases the item again."""
    decision = redispatch_progress_decision(
        limit=1,
        attempts=(
            _attempt(run_id="base"),
            _attempt(run_id="flat"),
            _attempt(run_id="advance", order=2, milestone="review"),
        ),
    )
    assert decision.refusal is None
    assert decision.non_progress_run_ids == ()


def test_a_failure_after_a_recovery_epoch_needs_a_recovery_naming_it() -> None:
    """The consumed recovery cannot be replayed against the longer history."""
    attempts = (_attempt(run_id="base"), _attempt(run_id="flat"), _attempt(run_id="again"))
    recovery = RedispatchRecovery(
        attempt_id="recovery-1",
        prior_run_ids=("flat",),
        diagnosis="stale fixture",
        operation="dispatch --item bd-ib-s5idxj",
        execution_evidence="receipt-1",
    )
    stale = redispatch_progress_decision(limit=1, attempts=attempts, recovery=recovery)
    fresh = redispatch_progress_decision(
        limit=1,
        attempts=attempts,
        recovery=RedispatchRecovery(
            attempt_id="recovery-2",
            prior_run_ids=("flat", "again"),
            diagnosis="fixture rebuilt",
            operation="dispatch --item bd-ib-s5idxj",
            execution_evidence="receipt-2",
        ),
    )
    assert stale.diagnosis == "causal recovery must name the refused non-progress run history"
    assert fresh.authorized_recovery_attempt_id == "recovery-2"

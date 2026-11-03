"""The causal recovery record admits exactly one otherwise-refused epoch."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchRecovery,
    redispatch_progress_decision,
)


def test_a_fresh_recovery_is_one_use_and_retains_the_flat_history() -> None:
    """The same stable recovery id cannot clear a second refusal."""
    attempts = (
        CompletedAttempt(
            run_id="baseline",
            terminal_cause="implement failed",
            high_water_milestone="implement",
            item_attributable=True,
        ),
        CompletedAttempt(
            run_id="flat",
            terminal_cause="review failed",
            high_water_milestone="implement",
            item_attributable=True,
        ),
    )
    recovery = RedispatchRecovery(
        attempt_id="recovery-1",
        prior_run_ids=("flat",),
        diagnosis="review fixture is stale",
        operation="dispatch --item bd-ib-s5idxj",
        execution_evidence="receipt-1",
    )

    admitted = redispatch_progress_decision(
        limit=1,
        attempts=attempts,
        recovery=recovery,
        consumed_recovery_attempt_ids=frozenset(),
    )
    replayed = redispatch_progress_decision(
        limit=1,
        attempts=attempts,
        recovery=recovery,
        consumed_recovery_attempt_ids=frozenset({"recovery-1"}),
    )

    assert admitted.refusal is None
    assert admitted.authorized_recovery_attempt_id == "recovery-1"
    assert admitted.non_progress_run_ids == ("flat",)
    assert replayed.refusal is not None
    assert replayed.authorized_recovery_attempt_id is None

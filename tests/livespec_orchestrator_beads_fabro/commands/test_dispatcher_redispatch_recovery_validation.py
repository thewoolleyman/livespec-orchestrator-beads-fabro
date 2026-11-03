"""Validation failures remain diagnoses, never a prose recovery bypass."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchRecovery,
    redispatch_progress_decision,
)


def test_incomplete_or_misaimed_recovery_keeps_the_guard_diagnostic() -> None:
    """Both a missing typed field and the wrong prior history refuse recovery."""
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
    incomplete = RedispatchRecovery(
        attempt_id="recovery-1",
        prior_run_ids=("flat",),
        diagnosis="",
        operation="dispatch --item bd-ib-s5idxj",
        execution_evidence="receipt-1",
    )
    misaimed = RedispatchRecovery(
        attempt_id="recovery-2",
        prior_run_ids=("other",),
        diagnosis="review fixture is stale",
        operation="dispatch --item bd-ib-s5idxj",
        execution_evidence="receipt-2",
    )

    incomplete_decision = redispatch_progress_decision(
        limit=1, attempts=attempts, recovery=incomplete
    )
    misaimed_decision = redispatch_progress_decision(limit=1, attempts=attempts, recovery=misaimed)

    assert incomplete_decision.diagnosis == "causal recovery requires measured diagnosis"
    assert (
        misaimed_decision.diagnosis
        == "causal recovery must name the refused non-progress run history"
    )

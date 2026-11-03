"""Across-dispatch progress decisions used by the admission valve."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_flat_item_failures_refuse_the_next_dispatch_with_their_evidence() -> None:
    """A baseline plus two flat attributable terminals exhausts a limit of two."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_redispatch_progress.py"
    )
    assert module_path.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress"
    )

    decision = module.redispatch_progress_decision(
        limit=2,
        attempts=(
            module.CompletedAttempt(
                run_id="01BASELINE",
                terminal_cause="implement failed",
                high_water_milestone="implement",
                item_attributable=True,
            ),
            module.CompletedAttempt(
                run_id="01FLATONE",
                terminal_cause="review failed",
                high_water_milestone="implement",
                item_attributable=True,
            ),
            module.CompletedAttempt(
                run_id="01FLATTWO",
                terminal_cause="test failed",
                high_water_milestone="implement",
                item_attributable=True,
            ),
        ),
    )

    assert decision.refusal is not None
    assert decision.refusal.run_ids == ("01FLATONE", "01FLATTWO")
    assert decision.refusal.causes == ("review failed", "test failed")
    assert decision.refusal.high_water_milestone == "implement"


def test_progress_host_failures_duplicates_and_active_runs_do_not_make_a_refusal() -> None:
    """Only comparable, attributable completed attempts consume the limit."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress"
    )

    decision = module.redispatch_progress_decision(
        limit=2,
        attempts=(
            module.CompletedAttempt(
                run_id="01BASELINE",
                terminal_cause="implement failed",
                high_water_milestone="implement",
                item_attributable=True,
            ),
            module.CompletedAttempt(
                run_id="01ADVANCED",
                terminal_cause="review failed",
                high_water_milestone="review",
                item_attributable=True,
            ),
            module.CompletedAttempt(
                run_id="01HOST",
                terminal_cause="factory lease lost",
                high_water_milestone="review",
                item_attributable=False,
            ),
            module.CompletedAttempt(
                run_id="01ACTIVE",
                terminal_cause="still running",
                high_water_milestone="review",
                item_attributable=True,
                completed=False,
            ),
            module.CompletedAttempt(
                run_id="01ADVANCED",
                terminal_cause="duplicate observation",
                high_water_milestone="review",
                item_attributable=True,
            ),
            module.CompletedAttempt(
                run_id="01FLAT",
                terminal_cause="review failed",
                high_water_milestone="review",
                item_attributable=True,
            ),
        ),
    )

    assert decision.refusal is None
    assert decision.non_progress_run_ids == ("01FLAT",)


def test_invalid_limit_and_unknown_or_incomparable_history_require_diagnosis() -> None:
    """A missing policy or uncertain classification never becomes a guessed count."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress"
    )

    invalid = module.redispatch_progress_decision(limit=0, attempts=())
    unknown = module.redispatch_progress_decision(
        limit=2,
        attempts=(
            module.CompletedAttempt(
                run_id="01UNKNOWN",
                terminal_cause="unclassified terminal",
                high_water_milestone="implement",
                item_attributable=None,
            ),
        ),
    )
    incomparable = module.redispatch_progress_decision(
        limit=2,
        attempts=(
            module.CompletedAttempt(
                run_id="01A",
                terminal_cause="failed",
                high_water_milestone="implement",
                item_attributable=True,
                workflow_identity="workflow-a",
            ),
            module.CompletedAttempt(
                run_id="01B",
                terminal_cause="failed",
                high_water_milestone="implement",
                item_attributable=True,
                workflow_identity="workflow-b",
            ),
        ),
    )

    assert invalid.diagnosis == "dispatcher.redispatch_no_progress_limit must be a positive integer"
    assert unknown.diagnosis == "01UNKNOWN has an unknown terminal cause"
    assert incomparable.diagnosis == "01B uses incomparable workflow workflow-b"

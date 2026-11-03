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

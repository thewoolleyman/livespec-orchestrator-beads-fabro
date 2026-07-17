"""Paired coverage for intake Definition-of-Ready routing evaluation."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.intake_dor import DefinitionOfReadyChecklist, evaluate


def test_evaluate_routes_epic_to_backlog() -> None:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )

    assert evaluate(checklist=checklist) == "backlog"


def test_evaluate_routes_complete_slice_to_pending_approval() -> None:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )

    assert evaluate(checklist=checklist) == "pending-approval"

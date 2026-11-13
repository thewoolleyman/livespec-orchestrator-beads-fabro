"""Tests for host-wide Fabro deletion pacing."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_an_active_factory_defers_ended_collection_by_default(tmp_path: Path) -> None:
    """The absent settings take the safe deferral default."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_rm_pacing.py"
    )
    assert module_path.is_file()
    pacing = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing"
    )
    journal: list[dict[str, object]] = []

    permitted = pacing.DeletionPacer(repo=tmp_path, now_epoch=lambda: 12.0).permit(
        factory="petri",
        run_id="01ENDED",
        caller="ended-run-collection",
        has_running_run=True,
        collection=True,
        journal=journal,
    )

    assert permitted is False
    assert journal == [
        {
            "stage": "fabro-rm-deferred",
            "run_id": "01ENDED",
            "factory": "petri",
            "caller": "ended-run-collection",
            "next_deletion_may_start_at": 12.0,
        }
    ]

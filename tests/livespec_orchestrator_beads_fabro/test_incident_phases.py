"""Canonical phase/lifecycle-state pairs."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._incident_phases import lifecycle_state_for


def test_drill_closed_pairs_with_done() -> None:
    assert lifecycle_state_for(phase="drill-closed") == "done"

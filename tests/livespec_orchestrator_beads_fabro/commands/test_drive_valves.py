"""Tests for the drive human-valve action cluster."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action


def test_run_human_valve_action_refuses_malformed_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = run_human_valve_action(repo=repo, action_id="approve:")

    assert result == {
        "action_id": "approve:",
        "kind": "human-valve",
        "status": "failed",
        "domain_error": "invalid-action-id",
        "summary": "Unsupported human valve action id.",
    }

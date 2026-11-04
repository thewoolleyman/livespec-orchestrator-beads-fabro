"""Regression coverage for the committed fleet-launch parity gates."""

from __future__ import annotations

from pathlib import Path


def test_launchers_assign_and_check_a_repository_hold_path() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "fleet-launch" / "config.sh").read_text(encoding="utf-8")
    dispatch = (root / "fleet-launch" / "dispatch-dual.sh").read_text(encoding="utf-8")
    resume = (root / "fleet-launch" / "resume-capped.sh").read_text(encoding="utf-8")

    assert "FLEET_LAUNCH_REPO_HOLD_DIR" in config
    assert "repo_hold_file" in dispatch
    assert "repo_hold_file" in resume


def test_launcher_declares_the_remaining_parity_gate_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "fleet-launch" / "config.sh").read_text(encoding="utf-8")
    dispatch = (root / "fleet-launch" / "dispatch-dual.sh").read_text(encoding="utf-8")
    resume = (root / "fleet-launch" / "resume-capped.sh").read_text(encoding="utf-8")
    ready_check = (root / "fleet-launch" / "ready-set-check.py").read_text(encoding="utf-8")

    assert "FLEET_LAUNCH_BREAKAGE_EXCEPTION_FILE" in config
    assert "FLEET_LAUNCH_GMK_TARGET_FILE" in config
    assert "FLEET_LAUNCH_GMK_CANDIDATE_CAP" in config
    assert "capacity" in ready_check
    assert "wip_green" in dispatch
    assert "re-ticket" in dispatch
    assert "re-ticket" in resume
    assert "candidate" in dispatch

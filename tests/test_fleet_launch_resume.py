"""Regression coverage for the capped provisional resume launcher."""

from __future__ import annotations

from pathlib import Path


def test_resume_launcher_is_committed_with_the_provisional_launchers() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    assert (repository_root / "fleet-launch" / "resume-capped.sh").is_file()

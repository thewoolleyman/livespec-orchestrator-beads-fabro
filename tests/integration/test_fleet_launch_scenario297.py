"""Integration coverage for Scenario 297's queued launcher preflight."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_DRIVER = _REPO_ROOT / "dev-tooling" / "just-check-fleet-launch.sh"
_TARGET_EXTRACTOR = _REPO_ROOT / "dev-tooling" / "aggregate-targets.sh"


def _run(*, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )


def test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate() -> None:
    """The shipped check proves queued preflight reuse, FIFO order, and failure cleanup."""
    targets = _run(argv=["bash", str(_TARGET_EXTRACTOR)])
    assert targets.returncode == 0, targets.stderr
    assert "check-fleet-launch" in targets.stdout.split()

    checked = _run(argv=["bash", str(_CHECK_DRIVER)])
    combined = checked.stdout + checked.stderr
    assert checked.returncode == 0, combined
    for assertion in (
        "the younger queued launcher starts its preflight before the older binds",
        "queued launchers bind in FIFO ticket order after their preflights",
        "a fresh queued preflight pass is reused when the younger launcher reaches the head",
        "a stale queued pass is re-run at the FIFO head before binding",
        "a failed queued preflight exits 4, drops its ticket, and never takes the mutex",
        "the mutex is released before either drive --action impl starts",
    ):
        assert assertion in combined, combined
    assert "0 failed" in combined, combined

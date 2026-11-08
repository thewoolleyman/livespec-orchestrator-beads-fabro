"""Regression coverage for the live Beads candidate lifecycle qualification."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATE_HARNESS = _REPO_ROOT / "bd-guard" / "test" / "run-v1-1-2-candidate-tests.sh"


def test_candidate_lifecycle_defer_date_is_computed_in_the_future() -> None:
    """The live qualification cannot become stale as the calendar advances."""
    harness_body = _CANDIDATE_HARNESS.read_text(encoding="utf-8")

    assert "defer_date=\"$(date -u -d ' +7 days' +%F)\"" in harness_body
    assert 'run_guard update q-life --defer "$defer_date"' in harness_body

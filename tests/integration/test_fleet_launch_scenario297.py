"""Integration coverage for Scenario 297's queued launcher preflight."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_DRIVER = _REPO_ROOT / "dev-tooling" / "just-check-fleet-launch.sh"
_TARGET_EXTRACTOR = _REPO_ROOT / "dev-tooling" / "aggregate-targets.sh"


_HARNESS = _REPO_ROOT / "fleet-launch" / "test" / "run-tests.sh"
_SLICE_FIRST_CASE_MARKER = "# --- 6. queued preflights"
_HANG_GUARD_SLACK_SECONDS = 120
_CEILING_CALL = re.compile(
    r"(?:wait_for_preflight\s+\S+\s+\d+|wait_for_line\s+\"[^\"]*\"\s+\"[^\"]*\"|await_both\s+\S+\s+\S+)\s+(\d+)"
)
_RETAINED_MARKER_WAIT = re.compile(r"\"\$waited\" -lt (\d+) \]; do sleep 1")
_SETTLE_SLEEP = re.compile(r"^sleep (\d+)$", re.MULTILINE)


def _run(*, argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def _declared_liveness_ceiling() -> int:
    declared = _run(argv=["bash", str(_HARNESS), "liveness-ceiling"])
    assert declared.returncode == 0, declared.stderr
    return int(declared.stdout.strip())


def test_scenario297_declared_liveness_ceiling_sums_the_slice_waits() -> None:
    """The harness's declared ceiling equals the sum of the per-wait bounds its slice carries."""
    slice_source = _HARNESS.read_text(encoding="utf-8").split(_SLICE_FIRST_CASE_MARKER, 1)[1]
    summed = (
        sum(int(bound) for bound in _CEILING_CALL.findall(slice_source))
        + sum(int(bound) for bound in _RETAINED_MARKER_WAIT.findall(slice_source))
        + sum(int(bound) for bound in _SETTLE_SLEEP.findall(slice_source))
    )
    assert _declared_liveness_ceiling() == summed


def test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate() -> None:
    """The shipped check proves queued preflight reuse, FIFO order, and failure cleanup."""
    targets = _run(argv=["bash", str(_TARGET_EXTRACTOR)])
    assert targets.returncode == 0, targets.stderr
    assert "check-fleet-launch" in targets.stdout.split()

    checked = _run(
        argv=["bash", str(_CHECK_DRIVER), "scenario297"],
        timeout=_declared_liveness_ceiling() + _HANG_GUARD_SLACK_SECONDS,
    )
    combined = checked.stdout + checked.stderr
    assert checked.returncode == 0, combined
    assert "shellcheck" not in combined.lower(), combined
    for assertion in (
        "the younger queued launcher starts its preflight before the older binds",
        "queued launchers bind in FIFO ticket order after their preflights",
        "a fresh queued preflight pass is reused when the younger launcher reaches the head",
        "a stale queued pass is re-run at the FIFO head before binding",
        "a failed queued preflight exits 4, drops its ticket, and never takes the mutex",
        "the mutex is released before either drive --action impl starts",
    ):
        assert assertion in combined, combined
    assert "--- 1. reads a stub factory board" not in combined, combined
    assert "0 failed" in combined, combined

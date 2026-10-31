"""Integration wiring for Scenario 269's bd-guard capture-server regression.

The shell harness owns the process-level observations: it starts the real
throwaway Python server, exercises a start delay longer than two seconds, and
forces a process exit that supplies standard error. This integration-tier test
binds that regression to the declared ``check-bd-guard`` target, so the scenario
cannot silently become a locally runnable but un-gated shell test.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _REPO_ROOT / "dev-tooling" / "just-check-bd-guard.sh"
_REGRESSION = _REPO_ROOT / "bd-guard" / "test" / "test-capture-start.sh"
_HARNESS = _REPO_ROOT / "bd-guard" / "test" / "run-tests.sh"


def test_scenario269_binds_the_declared_check_to_capture_start_observations() -> None:
    """The declared gate reaches both the slow-start and failure diagnostics."""
    check_body = _CHECK.read_text(encoding="utf-8")
    regression_body = _REGRESSION.read_text(encoding="utf-8")
    harness_body = _HARNESS.read_text(encoding="utf-8")

    assert "bash bd-guard/test/test-capture-start.sh" in check_body
    assert "CAPTURE_START_DELAY_SECONDS=2.1" in regression_body
    assert "CAPTURE_SERVER_FAIL_STATUS=23" in regression_body
    assert "exit status 23; stderr=synthetic capture startup failure" in regression_body
    assert '[ "$i" -lt 600 ]' in harness_body
    assert "capture_start_detail" in harness_body

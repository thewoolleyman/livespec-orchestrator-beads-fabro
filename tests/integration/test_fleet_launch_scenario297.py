"""Integration coverage for Scenario 297's queued launcher preflight."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_DRIVER = _REPO_ROOT / "dev-tooling" / "just-check-fleet-launch.sh"
_TARGET_EXTRACTOR = _REPO_ROOT / "dev-tooling" / "aggregate-targets.sh"

# A liveness guard against a hung harness, never a duration budget for its verdict.
_HARNESS_HANG_GUARD_SECONDS = 600


def _run(
    *, argv: list[str], environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=_HARNESS_HANG_GUARD_SECONDS,
    )


def _last_output(error: subprocess.TimeoutExpired) -> str:
    """Return all output captured before a subprocess stopped making progress."""
    output = (error.stdout, error.stderr)
    return (
        "\n".join(
            chunk.decode(errors="replace") if isinstance(chunk, bytes) else (chunk or "")
            for chunk in output
        ).strip()
        or "<no output captured>"
    )


def test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate() -> None:
    """The shipped check tolerates delayed preflights while proving FIFO behavior."""
    temporary_directory = TemporaryDirectory()
    delayed_launcher_startup = Path(temporary_directory.name) / "delayed-launcher-startup.sh"
    delayed_launcher_startup.write_text(
        '[ "${0##*/}" = "dispatch-dual.sh" ] && sleep 30\n', encoding="utf-8"
    )
    environment = {**os.environ, "BASH_ENV": str(delayed_launcher_startup)}

    targets = _run(argv=["bash", str(_TARGET_EXTRACTOR)], environment=environment)
    assert targets.returncode == 0, targets.stderr
    assert "check-fleet-launch" in targets.stdout.split()

    try:
        checked = _run(argv=["bash", str(_CHECK_DRIVER), "scenario297"], environment=environment)
    except subprocess.TimeoutExpired as error:
        pytest.fail(
            "".join(
                (
                    "Scenario 297 harness HUNG (it did not finish) after ",
                    f"_HARNESS_HANG_GUARD_SECONDS={_HARNESS_HANG_GUARD_SECONDS}; ",
                    f"harness last output:\n{_last_output(error)}",
                )
            )
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


def test_scenario297_timeout_reports_a_hung_harness_with_its_last_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard reports a hang and diagnostics; it is never a speed verdict."""
    results: list[subprocess.CompletedProcess[str] | subprocess.TimeoutExpired] = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="check-fleet-launch\n", stderr=""
        ),
        subprocess.TimeoutExpired(
            cmd="scenario297",
            timeout=_HARNESS_HANG_GUARD_SECONDS,
            output="queued preflight still running",
            stderr=b"last harness stderr",
        ),
    ]

    def timed_run(
        *, argv: list[str], environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        del argv, environment
        result = results.pop(0)
        if isinstance(result, subprocess.TimeoutExpired):
            raise result
        return result

    monkeypatch.setattr(sys.modules[__name__], "_run", timed_run)

    with pytest.raises(pytest.fail.Exception) as failure:
        test_scenario297_queued_preflight_harness_runs_from_the_check_aggregate()

    message = str(failure.value)
    assert "Scenario 297 harness HUNG (it did not finish)" in message
    assert f"_HARNESS_HANG_GUARD_SECONDS={_HARNESS_HANG_GUARD_SECONDS}" in message
    assert "harness last output:\nqueued preflight still running\nlast harness stderr" in message

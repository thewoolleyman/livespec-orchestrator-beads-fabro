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


def _run_wait_for_preflight(
    *, launcher_exits_during_first_read: bool
) -> subprocess.CompletedProcess[str]:
    """Run the harness's real wait_for_preflight against a scripted preflight record."""
    harness = _REPO_ROOT / "fleet-launch" / "test" / "run-tests.sh"
    launcher = (
        "sleep 30 & pid=$!" if launcher_exits_during_first_read else "true & pid=$!; sleep 0.3"
    )
    script = f"""
set -u
eval "$(sed -n '/^wait_for_preflight() {{/,/^}}/p' '{harness}')"
HARNESS_POLL_S=0.01
HARNESS_PREFLIGHT_HANG_GUARD_S=30
marker=$(mktemp -u)
preflight_count() {{
    if [ "{int(launcher_exits_during_first_read)}" = 1 ] && [ -e "$marker" ]; then echo 1; return; fi
    if [ "{int(launcher_exits_during_first_read)}" = 1 ]; then
        : > "$marker"
        kill "$pid"
        sleep 0.3
    fi
    echo 0
}}
log=$(mktemp)
echo 'launcher log line' > "$log"
{launcher}
wait_for_preflight the-case younger "$pid" "$log" the-item 1
rc=$?
if [ "$rc" -ne 0 ]; then echo "$PREFLIGHT_FAILURE_DETAIL"; fi
kill "$pid" 2>/dev/null
exit "$rc"
"""
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, check=False, text=True, timeout=60
    )


def test_scenario297_preflight_wait_accepts_a_launcher_that_preflighted_then_exited() -> None:
    """A launcher that records its preflight and exits mid-poll did reach its preflight."""
    reached_then_exited = _run_wait_for_preflight(launcher_exits_during_first_read=True)
    assert reached_then_exited.returncode == 0, reached_then_exited.stdout

    exited_without_preflight = _run_wait_for_preflight(launcher_exits_during_first_read=False)
    assert exited_without_preflight.returncode != 0
    for needle in (
        "case=the-case",
        "launcher=younger",
        "did not reach preflight",
        "launcher log line",
    ):
        assert needle in exited_without_preflight.stdout, exited_without_preflight.stdout


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

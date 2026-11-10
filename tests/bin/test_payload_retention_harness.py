"""Harness coverage for the payload-retention regression's own scaffolding.

`test_payload_retention_after_eviction.py` is the regression for work-item
`bd-ib-mtuqxb`. Its scaffolding carries arms that the happy path never reaches,
and this repository measures coverage over `tests/` too, so they cannot simply
be left unexercised:

- `_wait_for_ready`'s early-child-exit arm, which turns a child that dies before
  the startup handshake into an assertion carrying that child's own output;
- the test body's `finally`, which kills a child still alive after
  `communicate` timed out, so a wedged probe is not left running.

The handshake is a pipe the child writes one byte to, and the parent blocks
reading it until the byte arrives or the child's end closes, so which arm runs
is fixed by what the child does and never by how fast it does it. Every arm is
driven HERE against real disposable child processes (and, for the `finally`
arm, a deliberately hanging probe spliced in for the duration of one call). The
regression module is loaded by path so this file does not depend on how pytest
names it.

The probe splice is the only narrow control used: `_PROBE` and
`_DEFERRED_TIMEOUT_SECONDS` are module globals the regression's test body reads
at call time, so replacing them exercises the real body — the real `copytree`,
the real `Popen`, the real `rmtree`, the real `finally` — against a child that
announces readiness and then refuses to finish.

This is harness robustness, not product Red: it asserts nothing about
`_payload.py`. The spawns are real interpreters, so this file is listed in
`pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the coverage
subprocess hooks exactly as an allowlisted spawn must.
"""

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

_FROZEN_TEST_PATH = Path(__file__).resolve().parent / "test_payload_retention_after_eviction.py"
_FROZEN_MODULE_NAME = "frozen_payload_retention_regression"

# A child that exits immediately with a recognisable code and output, for the
# early-exit arm.
_DYING_CHILD = (
    "import sys; sys.stdout.write('child stdout\\n'); "
    "sys.stderr.write('child stderr\\n'); raise SystemExit(7)"
)

# The probe the `finally` arm needs: it completes the startup handshake, then
# never finishes, so `communicate` times out with the child still alive.
_HANGING_PROBE = """
import os
import signal
import sys

_, ready_fd, *_ = sys.argv[1:5]
os.write(int(ready_fd), b"1")
while True:
    signal.pause()
"""
_HANGING_TIMEOUT_SECONDS = 2.0
_DEAD_CHILD_EXIT = 7
_PATIENT_WAIT_SECONDS = 30.0


def _frozen_module() -> types.ModuleType:
    """Load the frozen regression by path, so its own module name is irrelevant."""
    spec = importlib.util.spec_from_file_location(_FROZEN_MODULE_NAME, _FROZEN_TEST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scrubbed_env() -> dict[str, str]:
    """The child environment an allowlisted spawn must use: no coverage hooks."""
    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    return {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }


def _spawn(*, code: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_scrubbed_env(),
    )


def test_wait_for_ready_reports_a_child_that_died_before_the_handshake() -> None:
    """A dead child must fail the regression WITH its own output, not hang."""
    module = _frozen_module()
    ready_read_fd, ready_write_fd = os.pipe()
    process = _spawn(code=_DYING_CHILD)
    # No child holds the write end, so the pipe is at end-of-file: the same
    # state a child that exits without writing leaves behind.
    os.close(ready_write_fd)
    _ = process.wait(timeout=_PATIENT_WAIT_SECONDS)
    try:
        with pytest.raises(AssertionError) as excinfo:
            module._wait_for_ready(  # noqa: SLF001 - the regression's own scaffolding is the subject.
                ready_fd=ready_read_fd,
                process=process,
            )
    finally:
        os.close(ready_read_fd)
    message = str(excinfo.value)
    assert f"child exited early (rc={_DEAD_CHILD_EXIT})" in message
    assert "child stdout" in message
    assert "child stderr" in message


def test_a_probe_that_never_finishes_is_killed_rather_than_left_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The regression's `finally` must reap a wedged probe.

    This drives the REAL frozen test body — real fixture copy, real child,
    real installation removal — with a probe that completes the handshake and
    then hangs. `communicate` raises `TimeoutExpired`, which propagates out of
    the body, and the `finally` is what stops the child from outliving the
    suite. The assertion is on the process, not on the exception.
    """
    module = _frozen_module()
    monkeypatch.setattr(module, "_PROBE", _HANGING_PROBE)
    monkeypatch.setattr(module, "_DEFERRED_TIMEOUT_SECONDS", _HANGING_TIMEOUT_SECONDS)
    spawned: list[subprocess.Popen[str]] = []
    real_popen = subprocess.Popen

    def _recording_popen(*args: object, **kwargs: object) -> subprocess.Popen[str]:
        process = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        spawned.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", _recording_popen)
    with pytest.raises(subprocess.TimeoutExpired):
        module.test_deferred_work_runs_from_the_retained_payload_after_the_install_is_removed(
            tmp_path=tmp_path
        )
    assert len(spawned) == 1, f"expected exactly one probe child, saw {len(spawned)}"
    assert spawned[0].poll() is not None, "the wedged probe was left running"

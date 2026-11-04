"""Test support for waiting until a fixture payload has exec'd."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

_PROC = Path("/proc")
_EXEC_TIMEOUT_SECONDS = 30.0
_POLL_SECONDS = 0.01


def _has_execd(*, cmdline: Path, entry: Path) -> bool:
    """Report whether `/proc/<pid>/cmdline` already names the payload entry."""
    try:
        return str(entry).encode() in cmdline.read_bytes().split(b"\0")
    except OSError:
        return False


def wait_for_dispatcher_exec(
    *,
    process: subprocess.Popen[bytes],
    entry: Path,
    proc: Path = _PROC,
    timeout_seconds: float = _EXEC_TIMEOUT_SECONDS,
    poll_seconds: float = _POLL_SECONDS,
) -> None:
    """Wait, within a fixed budget, for `/proc` to expose the payload argv."""
    deadline = time.monotonic() + timeout_seconds
    cmdline = proc / str(process.pid) / "cmdline"
    while not _has_execd(cmdline=cmdline, entry=entry):
        if time.monotonic() >= deadline:
            raise AssertionError(f"dispatcher fixture process {process.pid} did not exec {entry}")
        # real-time-required: /proc exposes a real child's exec only by polling it
        time.sleep(poll_seconds)

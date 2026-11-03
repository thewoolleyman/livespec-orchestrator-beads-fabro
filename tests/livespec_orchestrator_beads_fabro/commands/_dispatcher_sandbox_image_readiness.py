"""Test support for waiting until a fixture payload has exec'd."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

_PROC = Path("/proc")
_EXEC_TIMEOUT_SECONDS = 30.0
_POLL_SECONDS = 0.01


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
    while time.monotonic() < deadline:
        try:
            if str(entry).encode() in cmdline.read_bytes().split(b"\0"):
                return
        except OSError:
            pass
        time.sleep(poll_seconds)
    raise AssertionError(f"dispatcher fixture process {process.pid} did not exec {entry}")

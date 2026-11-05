"""Test support for confirming a fixture payload has exec'd."""

from __future__ import annotations

import subprocess
from pathlib import Path

_PROC = Path("/proc")


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
    timeout_seconds: float | None = None,
    poll_seconds: float | None = None,
) -> None:
    """Confirm `/proc` exposes the payload argv, with no waiting.

    `subprocess.Popen` returns only after the child's exec has completed, so the
    payload argv is already visible and one read settles it. The two budget
    arguments remain accepted for callers that still pass them; neither is read.
    """
    _ = (timeout_seconds, poll_seconds)
    if not _has_execd(cmdline=proc / str(process.pid) / "cmdline", entry=entry):
        raise AssertionError(f"dispatcher fixture process {process.pid} did not exec {entry}")

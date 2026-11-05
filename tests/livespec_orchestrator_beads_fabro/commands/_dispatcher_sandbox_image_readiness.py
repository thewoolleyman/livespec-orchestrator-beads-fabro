"""Test support for starting a dispatcher-argv fixture and waiting until it has exec'd."""

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
        time.sleep(poll_seconds)


def start_dispatcher_process(*, build: Path) -> subprocess.Popen[bytes]:
    """A real live process whose own argv names `<build>/scripts/bin/dispatcher.py`.

    That argv IS what identifies a running Dispatcher — every invocation of it
    goes through that one entry point — so the fixture only has to be a real
    process carrying it, and deliberately is NOT a Python child:
    `check-tests-no-subprocess-spawn` asks tests not to spawn one, and a real
    Dispatcher would need a factory and a tenant to get past its first argument.
    Returns only once `/proc` exposes that argv, so a scan of `/proc` never runs
    against a child that has forked but not yet exec'd.
    """
    entry = build / "scripts" / "bin" / "dispatcher.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    _ = entry.write_text("", encoding="utf-8")
    process = subprocess.Popen(["tail", "-f", "/dev/null", str(entry)])
    try:
        wait_for_dispatcher_exec(process=process, entry=entry)
    except BaseException:
        process.kill()
        _ = process.wait()
        raise
    return process

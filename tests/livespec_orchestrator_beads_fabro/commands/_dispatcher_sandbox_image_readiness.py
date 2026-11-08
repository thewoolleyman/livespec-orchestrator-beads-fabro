"""Test support for confirming a fixture payload has exec'd."""

from __future__ import annotations

import os
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


def _require_exec_signal(*, ready_read: int, process: subprocess.Popen[bytes]) -> None:
    """Require the wrapper event that proves its exec completed."""
    if os.read(ready_read, len(b"ready")) != b"ready":
        raise AssertionError(f"dispatcher fixture process {process.pid} did not signal exec")


def start_dispatcher_process(*, build: Path) -> subprocess.Popen[bytes]:
    """Start a fixture whose argv names `<build>/scripts/bin/dispatcher.py`.

    A private `tail` wrapper writes an inherited pipe only after the child has
    exec'd.  Receiving that event settles the otherwise racy `/proc` read:
    the wrapper's argv already names `entry`, and its final `exec tail` keeps
    the same argument in the long-lived fixture process.  This is a process
    event, not a host-clock poll.
    """
    entry = build / "scripts" / "bin" / "dispatcher.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    _ = entry.write_text("", encoding="utf-8")
    wrapper = build / "fixture-bin" / "tail"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    _ = wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        'os.write(int(os.environ["DISPATCHER_FIXTURE_READY_FD"]), b"ready")\n'
        'os.execv("/usr/bin/tail", ["/usr/bin/tail", *sys.argv[1:]])\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    ready_read, ready_write = os.pipe()
    env = dict(os.environ)
    env["PATH"] = f"{wrapper.parent}:{env.get('PATH', '')}"
    env["DISPATCHER_FIXTURE_READY_FD"] = str(ready_write)
    process = subprocess.Popen(
        ["tail", "-f", "/dev/null", str(entry)], env=env, pass_fds=(ready_write,)
    )
    os.close(ready_write)
    try:
        _require_exec_signal(ready_read=ready_read, process=process)
        wait_for_dispatcher_exec(process=process, entry=entry)
    except BaseException:
        process.kill()
        _ = process.wait()
        raise
    finally:
        os.close(ready_read)
    return process

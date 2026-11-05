"""Test support for starting a fixture process that names a dispatcher entry."""

from __future__ import annotations

import subprocess
from pathlib import Path

_READY_LINE = b"ready\n"
# `$0` is the entry path, so the shell's own argv names it for as long as the
# shell lives; it announces itself, then blocks reading stdin until killed.
_FIXTURE_SCRIPT = 'printf "ready\\n"; read _'


def await_dispatcher_ready(*, process: subprocess.Popen[bytes], entry: Path) -> None:
    """Block until the fixture shell has announced itself, or fail if it died first.

    The announcement is a line on the fixture's stdout, so this is a blocking
    read of an event the fixture produces once it is running with the entry in
    its argv. Nothing is polled, and a fixture that exits first closes the pipe,
    which reads as EOF here.
    """
    assert process.stdout is not None
    if process.stdout.readline() != _READY_LINE:
        raise AssertionError(f"dispatcher fixture process {process.pid} never announced {entry}")


def start_dispatcher_fixture(*, entry: Path) -> subprocess.Popen[bytes]:
    """A live shell whose own argv names `entry`, returned only once it is running."""
    process = subprocess.Popen(
        ["sh", "-c", _FIXTURE_SCRIPT, str(entry)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        await_dispatcher_ready(process=process, entry=entry)
    except BaseException:
        process.kill()
        _ = process.communicate()
        raise
    return process

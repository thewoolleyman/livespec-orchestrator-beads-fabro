"""The impure half of the Codex app-server renewal: one live conversation.

`_dispatcher_codex_early_renewal` owns what to SAY and how to CLASSIFY what
comes back, both pure. This module owns the process: spawn `codex app-server`,
keep stdin OPEN, send each request line and read until the answer carrying that
line's own id arrives, then close stdin and reap under a deadline.

Keeping stdin open is the whole point of the split. Measured on host codex
0.160.0 against a fresh empty `CODEX_HOME` with `refreshToken` false (no live
credential touched), writing all three lines at once and closing stdin
immediately exited 0 with only the id-1 `initialize` response and a status
notification — the `account/read` id 2 was never answered, because EOF cancels
the asynchronous request. A batch write therefore reports a spent renewal that
never happened, and exits 0 doing it.

The deadline is enforced by killing the process rather than by a read timeout:
a killed process makes the blocking `readline` return empty, which the drive
loop already handles as end-of-stream, so there is exactly one way out of the
loop instead of two.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import IO, Any, Literal, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    UNSPENDABLE_EXIT_CODE,
    classify_received_line,
    request_id_of,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "ShellCodexAppServerRunner",
]

# How long to let the server exit on its own after stdin closes before killing
# it. It has already answered everything we asked, so this is a reap bound, not
# a work bound.
_REAP_GRACE_SECONDS = 5.0


class ShellCodexAppServerRunner:
    """Production runner: one live `codex app-server` request/response session."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        request_lines: list[str],
        timeout_seconds: float,
    ) -> CommandResult:
        """Drive the conversation to its last answer, then terminate and reap."""
        spawned = attempt(
            action=lambda: subprocess.Popen(  # noqa: S603 - argv is Dispatcher-built, never shell
                argv,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # Never an unread PIPE: nothing here reads stderr, and a child
                # that fills that buffer blocks forever on its own write.
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                # Its OWN session, so the deadline can reap the whole tree.
                # Without this the group is the Dispatcher's, and killing it
                # would aim the signal at ourselves.
                start_new_session=True,
            ),
            exceptions=(OSError,),
        )
        if isinstance(spawned, AttemptFailure):
            return CommandResult(
                exit_code=UNSPENDABLE_EXIT_CODE,
                stdout="",
                stderr=f"codex app-server could not be started: {spawned.error}",
            )
        process = spawned
        # Kill the GROUP, not the launcher. `codex` on the orchestrator host is
        # a launcher that spawns the real binary with inherited stdio, so a
        # signal to the launcher alone leaves a grandchild holding the stdout
        # pipe and `readline` blocks until THAT process exits — measured at
        # 3.05s against a 0.5s deadline, and unbounded for a child that hangs.
        # Killing the group closes the pipe, which is what unblocks the read.
        watchdog = threading.Timer(timeout_seconds, lambda: _kill_tree(process=process))
        watchdog.start()
        try:
            return _converse(process=process, request_lines=request_lines)
        finally:
            watchdog.cancel()
            _reap(process=process)


def _converse(
    *,
    process: subprocess.Popen[str],
    request_lines: list[str],
) -> CommandResult:
    """Send each request line and await the answer carrying its own id."""
    stdin = cast("IO[str]", process.stdin)
    stdout = cast("IO[str]", process.stdout)
    transcript: list[str] = []
    for line in request_lines:
        written = _write_line(stream=stdin, line=line)
        if isinstance(written, AttemptFailure):
            return _unspendable(
                transcript=transcript,
                detail=f"writing {_method_of(line=line)} failed: {written.error}",
            )
        expected_id = request_id_of(line=line)
        if expected_id is None:
            # A notification is answered by nothing; awaiting one would block
            # until the deadline and report a timeout for a healthy session.
            continue
        answer = _await_answer(stdout=stdout, expected_id=expected_id, transcript=transcript)
        if answer != "answered":
            return _unspendable(
                transcript=transcript,
                detail=(
                    f"{_method_of(line=line)} (id {expected_id}) "
                    + (
                        "returned an error"
                        if answer == "errored"
                        else "was never answered; the session closed first"
                    )
                ),
            )
    return CommandResult(exit_code=0, stdout="".join(transcript), stderr="")


def _await_answer(
    *,
    stdout: IO[str],
    expected_id: int,
    transcript: list[str],
) -> Literal["answered", "errored", "closed"]:
    """Read lines until the answer for `expected_id` arrives or the stream ends."""
    while True:
        received = attempt(action=stdout.readline, exceptions=(OSError, ValueError))
        if isinstance(received, AttemptFailure) or not received:
            return "closed"
        transcript.append(received)
        kind = classify_received_line(line=received, expected_id=expected_id)
        if kind == "answered":
            return "answered"
        if kind == "errored":
            return "errored"


def _write_line(*, stream: IO[str], line: str) -> AttemptFailure | None:
    """Write one JSONL request and flush it, leaving stdin OPEN.

    `ValueError` is caught beside `OSError` because a pipe closed underneath us
    raises "I/O operation on closed file", which is a ValueError rather than an
    OSError — the same pair the read path catches.
    """
    return attempt(
        action=lambda: _flushed_write(stream=stream, line=line),
        exceptions=(OSError, ValueError),
    )


def _flushed_write(*, stream: IO[str], line: str) -> None:
    _ = stream.write(f"{line}\n")
    stream.flush()


def _method_of(*, line: str) -> str:
    """Name the method a request line carries, for a secret-free diagnostic.

    The input is always a line THIS package rendered, so a shape without a
    string `method` is a bug in the renderer and raises rather than degrading
    to a placeholder that would hide it.
    """
    message: dict[str, Any] = json.loads(line)
    return cast("str", message["method"])


def _unspendable(*, transcript: list[str], detail: str) -> CommandResult:
    """Report a conversation that did not complete, naming no credential value.

    The transcript is NOT carried into stderr. An app-server session can emit
    account state, so the diagnostic names the METHOD and the id and nothing
    the server said.
    """
    return CommandResult(
        exit_code=UNSPENDABLE_EXIT_CODE,
        stdout="".join(transcript),
        stderr=f"codex app-server renewal did not complete: {detail}",
    )


def _kill_tree(*, process: subprocess.Popen[str]) -> None:
    """SIGKILL the whole process group this runner started.

    Tolerates a group that has already gone: a tree that exited on its own
    leaves no group, and `ProcessLookupError` there is the NORMAL outcome of a
    healthy session rather than a fault worth surfacing.
    """
    killed = attempt(
        action=lambda: os.killpg(os.getpgid(process.pid), signal.SIGKILL),
        exceptions=(OSError,),
    )
    if isinstance(killed, AttemptFailure):
        # The group is gone; fall back to the direct handle so a process that
        # somehow escaped its own group is still not left running.
        _ = attempt(action=process.kill, exceptions=(OSError,))


def _reap(*, process: subprocess.Popen[str]) -> None:
    """Close stdin so the server exits, then wait, killing the tree if it lingers."""
    stdin = cast("IO[str]", process.stdin)
    _ = attempt(action=stdin.close, exceptions=(OSError,))
    waited = attempt(
        action=lambda: process.wait(timeout=_REAP_GRACE_SECONDS),
        exceptions=(subprocess.TimeoutExpired,),
    )
    if isinstance(waited, AttemptFailure):
        _kill_tree(process=process)
        _ = process.wait()

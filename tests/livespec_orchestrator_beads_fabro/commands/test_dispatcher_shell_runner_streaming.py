"""Regression coverage for the live-output command-runner seam."""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import TimeoutExpired
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_shell_runner
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)

# A deadline no passing run approaches: the real-child cases below end on an
# EVENT (the child's own exit, or a refused line), never on this clock. It sits
# far above interpreter startup on a loaded host, so a slow start cannot turn a
# passing case into a timeout; a wall-clock bound near startup time did exactly
# that at a load average of 85.
_UNREACHED_DEADLINE_SECONDS = 300.0


def test_streaming_runner_returns_complete_output_after_an_unrejected_stream(
    tmp_path: Path,
) -> None:
    """A normal stream preserves stdout, stderr, and the child's exit status."""
    seen: list[str] = []
    result = ShellCommandRunner().run_streaming(
        argv=[
            sys.executable,
            "-c",
            "import sys; print('one'); print('two'); sys.stderr.write('problem')",
        ],
        cwd=tmp_path,
        timeout_seconds=_UNREACHED_DEADLINE_SECONDS,
        on_stdout_line=lambda line: seen.append(line) and False,
    )

    assert result.exit_code == 0
    assert result.stdout == "one\ntwo\n"
    assert result.stderr == "problem"
    assert seen == ["one\n", "two\n"]


def test_streaming_runner_ends_the_child_when_the_callback_refuses_a_line(
    tmp_path: Path,
) -> None:
    """A refusal terminates before the candidate can emit a later natural verdict."""
    result = ShellCommandRunner().run_streaming(
        argv=[
            sys.executable,
            "-c",
            "import sys, time; print('limit', flush=True); time.sleep(3600); print('late')",
        ],
        cwd=tmp_path,
        timeout_seconds=_UNREACHED_DEADLINE_SECONDS,
        on_stdout_line=lambda line: line == "limit\n",
    )

    # The child would sleep past the deadline, so only the refusal can end it
    # with something other than the timeout result.
    assert result.exit_code not in (0, 124)
    assert "timeout after" not in result.stderr
    assert result.stdout == "limit\n"
    assert "late" not in result.stdout


def test_streaming_runner_ends_only_the_candidates_own_session_group(
    tmp_path: Path,
) -> None:
    """The REAL termination reaps the candidate's group and spares the caller's.

    The one case here that drives `os.killpg` with a genuine process group rather
    than a double's number, which is why it is the only one that can establish
    the invariant the rest of the module merely avoids violating: a candidate's
    group is PRIVATE to the candidate, so ending it cannot reach the process that
    started it.

    The candidate reports its OWN group on its first line and the observer
    refuses that line, which is what makes the group knowable from out here --
    `run_streaming` exposes no pid, and asserting on one the test had chosen
    would assert about a process the runner never had. `start_new_session=True`
    is the runner's own, not this test's: the assertion that the reported group
    differs from `os.getpgrp()` is what proves the runner really did give the
    candidate a private session, and without it every later assertion would hold
    just as well for a runner that had signalled its caller's group and happened
    to survive.

    Both directions are read, because either alone is satisfied by a wrong
    implementation: a runner that signalled NOTHING leaves this process alive,
    and a runner that signalled EVERYTHING would have taken this process down
    with the candidate -- which is not a failure a test can report, so the
    surviving half of the pair is the half that has to be asserted positively.
    """
    own_group = os.getpgrp()
    reported: list[int] = []

    def refuse_once_the_group_is_known(*, line: str) -> bool:
        reported.append(int(line.strip()))
        return True

    result = ShellCommandRunner().run_streaming(
        argv=[
            sys.executable,
            "-c",
            "import os, time; print(os.getpgrp(), flush=True); time.sleep(3600)",
        ],
        cwd=tmp_path,
        timeout_seconds=_UNREACHED_DEADLINE_SECONDS,
        on_stdout_line=refuse_once_the_group_is_known,
    )

    assert reported, "the candidate never reported its own process group"
    candidate_group = reported[0]
    assert candidate_group != own_group, (
        "the runner left the candidate in this process's group, so ending the"
        " candidate would have ended the caller"
    )
    assert result.exit_code != 0
    # The candidate's group is gone -- signal 0 asks whether it exists and sends
    # nothing, so this probe cannot itself terminate anything.
    with pytest.raises(ProcessLookupError):
        os.killpg(candidate_group, 0)
    # ...and this process's own group is untouched.
    os.killpg(own_group, 0)


def test_streaming_runner_maps_an_unfinished_stream_to_the_timeout_result(
    tmp_path: Path,
) -> None:
    """A candidate that emits no closing stream before its deadline is routable data."""
    result = ShellCommandRunner().run_streaming(
        argv=[sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        timeout_seconds=0.05,
        on_stdout_line=lambda line: line == "",
    )

    assert result.exit_code == 124
    assert "timeout after 0.05s" in result.stderr


def test_streaming_runner_maps_an_absent_executable_without_starting_a_stream(
    tmp_path: Path,
) -> None:
    """The streaming entry point uses the same routable launch-failure contract."""
    result = ShellCommandRunner().run_streaming(
        argv=["livespec-no-such-streaming-binary-xyz"],
        cwd=tmp_path,
        timeout_seconds=2.0,
        on_stdout_line=lambda line: line == "",
    )

    assert result.exit_code == 127
    assert "executable not found" in result.stderr


class _ImmediateThread:
    """A reader thread whose target runs synchronously for deterministic cleanup tests."""

    def __init__(self, *, target: object, daemon: bool) -> None:
        self._target = cast(Callable[[], None], target)
        self._daemon = daemon

    def start(self) -> None:
        self._target()

    def join(self) -> None:
        return None


# The group number a double below names. It is deliberately ABOVE this kernel's
# `pid_max`, so no process group can ever carry it and the real `os.killpg` can
# only answer `ESRCH` -- which `_terminate_process_group` already catches. That
# is defence in depth rather than the guarantee: `_use_process` installs
# `_SignalLog` in place of `os.killpg` for every double-driven case, and THAT is
# what keeps a fabricated pid away from the syscall.
#
# It was 1 until 2026-10-27, and 1 is a live group -- in a container it is
# init's. The timeout case below patches neither `IS_POSIX` nor `os.killpg`, so
# the real group signal reached init, which tore down the whole sandbox. Four
# implement turns in a row died that way, and each was reported only as the
# agent process exiting before the protocol completed on signal 15 -- a
# sentence that names nothing about this file.
_UNRESOLVABLE_GROUP = 1 << 30


class _ClosedStreamsProcess:
    """The minimal completed process whose two pipes are unavailable.

    Both pipes are `None`, which is what `Popen` leaves behind once a child's
    streams are closed and the shape the runner's two reader functions each
    guard against. An empty in-memory buffer stands in for a pipe that is OPEN
    and has nothing to say, which is a different condition reaching the other
    side of both guards -- and the real-child cases above already cover that one.
    """

    pid = _UNRESOLVABLE_GROUP
    returncode = 0

    def __init__(self) -> None:
        self.stdout = None
        self.stderr = None


class _WaitTimeoutProcess(_ClosedStreamsProcess):
    """A closed stream whose process remains live until the timeout cleanup runs."""

    def wait(self, timeout: float | None = None) -> int:
        if timeout is not None:
            raise TimeoutExpired(cmd="judge", timeout=timeout)
        return self.returncode


class _TerminationProcess(_ClosedStreamsProcess):
    """A process stand-in that records the platform-specific cleanup methods."""

    pid = _UNRESOLVABLE_GROUP

    def __init__(self, *, poll_result: int | None = None) -> None:
        super().__init__()
        self.poll_result = poll_result
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def poll(self) -> int | None:
        return self.poll_result


class _EscalatingProcess(_TerminationProcess):
    """A child that ignores every BOUNDED wait, so only a forced kill reaps it.

    Keyed on whether the wait carries a deadline rather than on how many waits
    have happened, which is what makes the escalation reachable: the runner takes
    two bounded waits before it forces anything -- one to notice the deadline, one
    to give the graceful stop its moment -- so a double that relents on its second
    call returns from the second of those and `_kill_process_group` is never
    reached at all. A call count also hard-codes the runner's current number of
    waits, so inserting one anywhere would silently move which call relents.
    """

    def __init__(self, *, poll_result: int | None = None) -> None:
        super().__init__(poll_result=poll_result)
        self.wait_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if timeout is not None:
            raise TimeoutExpired(cmd="judge", timeout=timeout)
        return 0


def test_streaming_runner_covers_closed_pipes_and_timeout_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public seam closes pipes and maps a live child to the timeout result."""
    process = _WaitTimeoutProcess()
    signals = _use_process(monkeypatch=monkeypatch, process=process)
    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda line: line == "",
    )

    assert result.exit_code == 124
    assert "timeout after 1.0s" in result.stderr
    assert process.wait() == 0
    # Every group it reached is the double's own, never this process's. This case
    # patches neither `IS_POSIX` nor `os.killpg`, so it is the one that used to
    # take the real syscall all the way to process group 1. The pair is the
    # escalation: a graceful stop first, then a forced one, because this double
    # never completes its bounded wait.
    assert signals.signalled == [
        (_UNRESOLVABLE_GROUP, signal.SIGTERM),
        (_UNRESOLVABLE_GROUP, signal.SIGKILL),
    ]
    assert os.getpgrp() not in signals.groups


def test_streaming_runner_covers_windows_and_posix_cleanup_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public seam tolerates vanished groups and escalates only live children.

    A child the runner had to FORCE down never reported an exit status of its
    own, so both halves end on the timeout result rather than on 0. That is the
    runner's contract for an unfinished stream and is what the two halves have in
    common; what separates them is which mechanism was reached, which is the only
    thing either half is evidence about.
    """
    process = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(_dispatcher_shell_runner, "IS_POSIX", False)

    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda line: line != "",
    )

    # Off POSIX there is no group to signal, so the escalation runs through the
    # process object's own two methods.
    assert result.exit_code == 124
    assert process.terminated is True
    assert process.killed is True
    # One wait to notice the deadline, one to give the graceful stop its moment,
    # and the unbounded one that finally reaps it.
    assert process.wait_calls == 3

    vanished = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=vanished)
    monkeypatch.setattr(_dispatcher_shell_runner, "IS_POSIX", True)
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", _raise_process_lookup)
    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda line: line != "",
    )

    # A group that vanished between the poll and the signal is already gone, so
    # neither fallback is reached: there is nothing left to terminate.
    assert result.exit_code == 124
    assert vanished.terminated is False
    assert vanished.killed is False


def test_streaming_runner_falls_back_after_a_process_group_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A still-live child receives direct termination and kill when killpg refuses.

    Paired with the already-exited child below, and neither case means anything
    alone: the fallback is guarded by a `poll()`, so an implementation that
    terminated UNCONDITIONALLY satisfies this half, and one that never fell back
    at all satisfies the other.
    """
    process = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", _raise_os_error)

    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda line: line != "",
    )

    assert result.exit_code == 124
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 3


def test_streaming_runner_leaves_an_already_exited_child_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused `killpg` over a child that already exited reaches no fallback.

    The other half of the `poll()` guard above. `poll()` answering a status means
    the child is already reaped, so terminating it would be signalling whatever
    the operating system has since done with that pid.
    """
    process = _EscalatingProcess(poll_result=0)
    _use_process(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", _raise_os_error)

    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda line: line != "",
    )

    assert result.exit_code == 124
    assert process.terminated is False
    assert process.killed is False


def test_the_signal_log_refuses_this_processs_own_group() -> None:
    """The guard that makes every double-driven case safe is itself graded.

    The POSITIVE CONTROL for this module. Each case above asserts that the
    runner did not signal this process's group, and a recorder that accepted
    every group would satisfy all of them while catching nothing — so without
    this case those assertions establish only that the instrument runs, not
    that it can fail.

    It is also the one condition here that no other case could observe: a real
    self-signal ends the process that would have reported it, so the only way
    to see the refusal is to ask the recorder for it directly.
    """
    log = _SignalLog()

    with pytest.raises(AssertionError, match="own process group"):
        log.killpg(os.getpgrp(), signal.SIGTERM)

    # Refused rather than recorded: a logged self-signal would read downstream
    # as a group the runner was entitled to end.
    assert log.signalled == []


def _raise_process_lookup(*_args: object) -> None:
    raise ProcessLookupError


def _raise_os_error(*_args: object) -> None:
    raise OSError


class _SignalLog:
    """A stand-in `os.killpg` that records groups and REFUSES the caller's own.

    Installed for every double-driven case, because a double's pid names no
    session this suite owns and signalling whatever group happens to carry that
    number is not this module's to do. A self-signal becomes a failing assertion
    here rather than a dead test runner -- which is the one outcome a test cannot
    report, since the process that would report it is the process being killed.
    """

    def __init__(self) -> None:
        self.signalled: list[tuple[int, int]] = []

    @property
    def groups(self) -> list[int]:
        """Each group signalled, in order, with repeats kept for the escalation."""
        return [pgid for pgid, _ in self.signalled]

    def killpg(self, pgid: int, signal_number: int) -> None:
        """Record one signalled group, refusing the group this process belongs to."""
        if pgid == os.getpgrp():
            message = (
                f"the runner signalled the test runner's own process group {pgid}; "
                "a candidate's group must be private to the candidate"
            )
            raise AssertionError(message)
        self.signalled.append((pgid, signal_number))


def _use_process(*, monkeypatch: pytest.MonkeyPatch, process: object) -> _SignalLog:
    """Drive the public runner with a deterministic process and synchronous readers.

    Returns the signal log that stands in for `os.killpg`, so a case may read
    which groups were signalled. A case needing a particular `killpg` FAILURE
    patches over this one, which is why the log is installed first.
    """
    monkeypatch.setattr(_dispatcher_shell_runner.threading, "Thread", _ImmediateThread)
    signals = _SignalLog()
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", signals.killpg)

    def launch(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        return process

    monkeypatch.setattr(_dispatcher_shell_runner.subprocess, "Popen", launch)
    return signals

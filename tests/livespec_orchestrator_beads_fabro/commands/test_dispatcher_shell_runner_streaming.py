"""Regression coverage for the live-output command-runner seam."""

from __future__ import annotations

import io
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
        timeout_seconds=2.0,
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
            "import sys, time; print('limit', flush=True); time.sleep(10); print('late')",
        ],
        cwd=tmp_path,
        timeout_seconds=2.0,
        on_stdout_line=lambda line: line == "limit\n",
    )

    assert result.exit_code != 0
    assert result.stdout == "limit\n"
    assert "late" not in result.stdout


def test_streaming_runner_maps_an_unfinished_stream_to_the_timeout_result(
    tmp_path: Path,
) -> None:
    """A candidate that emits no closing stream before its deadline is routable data."""
    result = ShellCommandRunner().run_streaming(
        argv=[sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        timeout_seconds=0.05,
        on_stdout_line=lambda _line: False,
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
        on_stdout_line=lambda _line: False,
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


class _ClosedStreamsProcess:
    """The minimal completed process whose two pipes are unavailable."""

    pid = 1
    returncode = 0

    def __init__(self) -> None:
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        return self.returncode


class _WaitTimeoutProcess(_ClosedStreamsProcess):
    """A closed stream whose process remains live until the timeout cleanup runs."""

    def wait(self, timeout: float | None = None) -> int:
        if timeout is not None:
            raise TimeoutExpired(cmd="judge", timeout=timeout)
        return self.returncode


class _TerminationProcess(_ClosedStreamsProcess):
    """A process stand-in that records the platform-specific cleanup methods."""

    pid = 1

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
    """A process that needs a forced kill before its wait can complete."""

    def __init__(self) -> None:
        super().__init__()
        self.wait_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise TimeoutExpired(cmd="judge", timeout=timeout)
        return 0


def test_streaming_runner_covers_closed_pipes_and_timeout_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public seam closes pipes and maps a live child to the timeout result."""
    process = _WaitTimeoutProcess()
    _use_process(monkeypatch=monkeypatch, process=process)
    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda _line: False,
    )

    assert result.exit_code == 124
    assert "timeout after 1.0s" in result.stderr
    assert process.wait() == 0


def test_streaming_runner_covers_windows_and_posix_cleanup_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public seam tolerates vanished groups and escalates only live children."""
    process = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(_dispatcher_shell_runner, "IS_POSIX", False)

    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda _line: True,
    )

    assert result.exit_code == 0
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2

    vanished = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=vanished)
    monkeypatch.setattr(_dispatcher_shell_runner, "IS_POSIX", True)
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", _raise_process_lookup)
    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda _line: True,
    )

    assert result.exit_code == 0
    assert vanished.terminated is False
    assert vanished.killed is False


def test_streaming_runner_falls_back_after_a_process_group_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A still-live child receives direct termination and kill when killpg refuses."""
    process = _EscalatingProcess()
    _use_process(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(_dispatcher_shell_runner.os, "killpg", _raise_os_error)

    result = ShellCommandRunner().run_streaming(
        argv=["judge"],
        cwd=Path.cwd(),
        timeout_seconds=1.0,
        on_stdout_line=lambda _line: True,
    )

    assert result.exit_code == 0
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2


def _raise_process_lookup(*_args: object) -> None:
    raise ProcessLookupError


def _raise_os_error(*_args: object) -> None:
    raise OSError


def _use_process(*, monkeypatch: pytest.MonkeyPatch, process: object) -> None:
    """Drive the public runner with a deterministic process and synchronous readers."""
    monkeypatch.setattr(_dispatcher_shell_runner.threading, "Thread", _ImmediateThread)

    def launch(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        return process

    monkeypatch.setattr(_dispatcher_shell_runner.subprocess, "Popen", launch)

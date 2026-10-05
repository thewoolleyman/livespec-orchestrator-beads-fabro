"""Conversation-lifecycle tests for the Codex app-server renewal transport.

These exist because a fake that merely RECORDS the request lines cannot catch
the defect they were written for. Measured on host codex 0.160.0, against a
fresh empty `CODEX_HOME` with `refreshToken` false so no live credential was
touched: writing all three request lines at once and closing stdin immediately
exits 0 having emitted only the id-1 `initialize` response plus a status
notification, and NEVER an id-2 `account/read` response — EOF cancels the
asynchronous request. The control that keeps stdin open, awaits id 1, then
sends `initialized` and `account/read` and awaits id 2, receives id 2 normally.

So the fake below is a DUPLEX process: it answers a request only if that
request actually arrived while stdin was open, and it stops answering once
stdin closes. A transport that batches and closes gets no id-2 answer from it,
exactly as the real server behaves.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_app_server_io
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_app_server_io import (
    ShellCodexAppServerRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    UNSPENDABLE_EXIT_CODE,
    codex_app_server_argv,
    codex_early_renewal_request_lines,
    request_early_codex_renewal,
)

_ACCOUNT_STATE_NOTIFICATION = json.dumps(
    {"jsonrpc": "2.0", "method": "account/updated", "params": {"plan": "pro"}}
)


class _FakeStdin:
    """A stdin pipe that records writes and refuses them once closed."""

    def __init__(self, *, process: _FakeAppServer) -> None:
        self._process = process
        self.closed = False

    def write(self, text: str) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file")
        self._process.receive(text=text)
        return len(text)

    def flush(self) -> None:
        """A flush on this fake is a no-op; `write` is what refuses when closed."""

    def close(self) -> None:
        self.closed = True


class _FakeStdout:
    """A stdout pipe draining whatever the fake server has queued."""

    def __init__(self, *, process: _FakeAppServer) -> None:
        self._process = process

    def readline(self) -> str:
        return self._process.emit()


class _FakeAppServer:
    """A duplex `codex app-server` stand-in driven by what it actually receives.

    It answers an id only when the request carrying that id arrived over an
    OPEN stdin, which is the property the batched-write defect violates. It
        also interleaves a server notification ahead of the id-2 answer, so a
    reader that took the first line it saw would accept the notification.
    """

    def __init__(
        self,
        *,
        error_on_id: int | None = None,
        notify_before_account: bool = True,
        answer_ids: frozenset[int] | None = None,
    ) -> None:
        self._error_on_id = error_on_id
        self._notify_before_account = notify_before_account
        self._answer_ids = answer_ids
        self._pending: list[str] = []
        self.received_methods: list[str] = []
        self.killed = False
        self.waited = False
        self.returncode: int | None = None
        self.stdin = _FakeStdin(process=self)
        self.stdout = _FakeStdout(process=self)
        self.stderr = None

    # -- the server side -------------------------------------------------
    def receive(self, *, text: str) -> None:
        for raw in text.splitlines():
            message = json.loads(raw)
            method = message["method"]
            self.received_methods.append(method)
            request_id = message.get("id")
            if request_id is None:
                continue
            if self._answer_ids is not None and request_id not in self._answer_ids:
                continue
            if method == "account/read" and self._notify_before_account:
                self._pending.append(_ACCOUNT_STATE_NOTIFICATION)
            if request_id == self._error_on_id:
                self._pending.append(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32000, "message": "refresh declined"},
                        }
                    )
                )
                continue
            self._pending.append(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {}}))

    def emit(self) -> str:
        if not self._pending:
            # Nothing queued means the request was never processed: the real
            # server's stream ends rather than blocking forever here.
            return ""
        return f"{self._pending.pop(0)}\n"

    # -- the process side ------------------------------------------------
    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        self.waited = True
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


def _install(
    *,
    monkeypatch: pytest.MonkeyPatch,
    process: _FakeAppServer,
) -> list[tuple[list[str], str]]:
    spawns: list[tuple[list[str], str]] = []

    def popen(argv: list[str], **kwargs: object) -> _FakeAppServer:
        spawns.append((argv, str(kwargs["cwd"])))
        return process

    monkeypatch.setattr(_dispatcher_codex_app_server_io.subprocess, "Popen", popen)
    return spawns


def test_account_read_is_sent_only_after_the_initialize_answer_arrives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The full handshake completes over one OPEN stdin, in protocol order."""
    process = _FakeAppServer()
    spawns = _install(monkeypatch=monkeypatch, process=process)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == 0
    assert spawns == [(codex_app_server_argv(), str(tmp_path))]
    # Every line reached the server, in order, over a stdin that stayed open.
    assert process.received_methods == ["initialize", "initialized", "account/read"]
    # stdin is closed only after the conversation, and the process is reaped.
    assert process.stdin.closed is True
    assert process.waited is True


def test_a_server_notification_is_not_mistaken_for_the_account_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An interleaved notification is skipped; the id-2 response is the answer."""
    process = _FakeAppServer(notify_before_account=True)
    _ = _install(monkeypatch=monkeypatch, process=process)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == 0
    # The notification WAS emitted ahead of the answer, so the skip is real
    # rather than a case the fake never exercised.
    assert _ACCOUNT_STATE_NOTIFICATION in result.stdout
    assert '"id": 2' in result.stdout


def test_an_unanswered_account_read_is_reported_unspendable_not_successful(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The measured batched-EOF failure mode cannot be reported as success.

    The fake answers id 1 and refuses to answer id 2, which is exactly what
    the real server does when EOF cancels the asynchronous request. A transport
    that reported the process exit code would return 0 here.
    """
    process = _FakeAppServer(answer_ids=frozenset({1}))
    _ = _install(monkeypatch=monkeypatch, process=process)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "account/read" in result.stderr
    assert "never answered" in result.stderr
    # The diagnostic names the method and the id, never what the server said.
    assert "pro" not in result.stderr


def test_an_error_response_is_reported_unspendable_without_quoting_the_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A JSON-RPC error on the renewal refuses, carrying no server payload."""
    process = _FakeAppServer(error_on_id=2)
    _ = _install(monkeypatch=monkeypatch, process=process)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "account/read" in result.stderr
    assert "returned an error" in result.stderr
    assert "refresh declined" not in result.stderr


def test_a_failed_handshake_stops_before_requesting_the_renewal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An id-1 error ends the session; no renewal is requested after it."""
    process = _FakeAppServer(error_on_id=1)
    _ = _install(monkeypatch=monkeypatch, process=process)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "initialize" in result.stderr
    assert "account/read" not in process.received_methods


def test_the_deadline_kills_the_session_rather_than_blocking_on_a_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A server that answers nothing is killed by the watchdog and reported."""
    process = _FakeAppServer(answer_ids=frozenset())
    _ = _install(monkeypatch=monkeypatch, process=process)

    result = ShellCodexAppServerRunner().run(
        argv=codex_app_server_argv(),
        cwd=tmp_path,
        request_lines=codex_early_renewal_request_lines(),
        timeout_seconds=0.05,
    )

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "initialize" in result.stderr


def test_a_write_that_fails_midway_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stdin that closes under us refuses; the dispatch never sees a traceback."""
    process = _FakeAppServer()
    _ = _install(monkeypatch=monkeypatch, process=process)
    process.stdin.close()

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "initialize" in result.stderr
    assert "failed" in result.stderr


def test_an_unspawnable_app_server_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A missing `codex` binary refuses; it is not an authentication verdict."""

    def popen(argv: list[str], **kwargs: object) -> _FakeAppServer:
        _ = (argv, kwargs)
        raise FileNotFoundError("codex")

    monkeypatch.setattr(_dispatcher_codex_app_server_io.subprocess, "Popen", popen)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == UNSPENDABLE_EXIT_CODE
    assert "could not be started" in result.stderr


def test_a_lingering_session_is_killed_during_the_reap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A server that will not exit after stdin closes is killed, never left."""
    process = _FakeAppServer()
    waits: list[float | None] = []

    def wait(timeout: float | None = None) -> int:
        waits.append(timeout)
        if len(waits) == 1:
            raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout or 0.0)
        return 0

    _ = _install(monkeypatch=monkeypatch, process=process)
    monkeypatch.setattr(process, "wait", wait)

    result = request_early_codex_renewal(cwd=tmp_path, runner=ShellCodexAppServerRunner())

    assert result.exit_code == 0
    assert process.killed is True
    assert len(waits) == 2

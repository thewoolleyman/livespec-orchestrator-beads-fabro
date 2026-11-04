"""The availability-evidence reader takes a run's record by a bounded, compressed read.

bd-ib-fhmpik: one failed petri run (01M6G8QJR80VH8T53MBGVEBP9E) carried a
10.4 MB record, 8.6 MB of it one stage's command output. `fabro inspect --json`
sends no `Accept-Encoding` and gives up at its own fixed 30 s, so the read
answered "unreadable" and `_row_unreadable` blanked every Anthropic and Codex
candidate fleet-wide for about 13 minutes. The same record taken from the
server's `/api/v1/runs/{id}/state` route with gzip arrived in 0.92 s.

These tests pin the reader's side of that: the record is read from the server
route, compressed, under a bounded per-attempt time; a read that gets no answer
is retried once inside the same evaluation, and every attempt that got no
answer is journaled with its run, factory and elapsed seconds.
"""

from __future__ import annotations

import gzip
import importlib
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_SERVER = "https://petri.example.ts.net:32276"
_RUN_ID = "01M6G8QJR80VH8T53MBGVEBP9E"
_STATE_URL = f"{_SERVER}/api/v1/runs/{_RUN_ID}/state"
# The 30 s the engine CLI gives up at; a bounded attempt must finish inside it.
_CLI_TIMEOUT_SECONDS = 30.0

# The record as the server's state route returns it: `checkpoints[]` wrapping
# each state, NO top-level `checkpoint`, and no `run_id`. The inspect CLI's
# shape carries both, and the graders read the top-level `checkpoint`.
_STATE_RECORD: dict[str, object] = {
    "status": {"kind": "failed", "reason": "workflow_error"},
    "conclusion": {"failure": {"reason": "workflow_error", "detail": {"message": "x"}}},
    "checkpoints": [
        {"seq": 7, "checkpoint": {"current_node": "fix", "node_outcomes": {}}},
        {"seq": 9, "checkpoint": {"current_node": "pr_refresh", "node_outcomes": {}}},
    ],
    "stages": {"pr_refresh@1": {"handler": "command", "output": "x" * 4096, "state": "failed"}},
}


def _module(*, name: str) -> Any:
    path = _COMMANDS / f"{name}.py"
    assert path.is_file(), f"{name}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _repo(*, tmp_path: Path) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {"petri": {"bin": "/factory/fabro", "server": _SERVER}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _answered(*, payload: object, status: int = 200) -> FabroHttpResult:
    return FabroHttpResult(
        status=status,
        body=json.dumps(payload),
        error=None,
        payload=None,
        succeeded=200 <= status < 300,
    )


def _no_answer() -> FabroHttpResult:
    return FabroHttpResult(
        status=0,
        body="",
        error="TimeoutError: the read exceeded its 20.0 s bound",
        payload=None,
        succeeded=False,
    )


@dataclass(kw_only=True)
class _ScriptedTransport:
    results: list[FabroHttpResult]
    calls: list[dict[str, object]] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        self.calls.append({"method": method, "url": url, "timeout_seconds": timeout_seconds})
        _ = (headers, body)
        return self.results.pop(0)


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return self.results.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Clock:
    """A monotonic clock that advances a fixed step on every reading."""

    step: float
    now: float = 0.0

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def _reader(
    *, tmp_path: Path, transport: _ScriptedTransport, runner: _Runner, journal: _Journal
) -> Any:
    module = _module(name="_acp_factory_run_reader")
    return module.FactoryRunReader(
        repo=_repo(tmp_path=tmp_path),
        runner=runner,
        http_transport=transport,
        journal=journal,
        clock=_Clock(step=12.5),
    )


def test_the_record_is_read_from_the_state_route_inside_the_cli_bound(tmp_path: Path) -> None:
    """One bounded server read answers, and the engine CLI is never spawned."""
    transport = _ScriptedTransport(results=[_answered(payload=_STATE_RECORD)])
    runner = _Runner(results=[])
    journal = _Journal()

    payload = _reader(
        tmp_path=tmp_path, transport=transport, runner=runner, journal=journal
    ).inspect_payload(factory="petri", run_id=_RUN_ID)

    assert [(call["method"], call["url"]) for call in transport.calls] == [("GET", _STATE_URL)]
    timeout = transport.calls[0]["timeout_seconds"]
    assert isinstance(timeout, float)
    assert timeout < _CLI_TIMEOUT_SECONDS
    assert runner.calls == []
    assert journal.records == []
    assert isinstance(payload, dict)
    assert payload["run_id"] == _RUN_ID
    assert payload["checkpoint"] == {"current_node": "pr_refresh", "node_outcomes": {}}
    assert payload["conclusion"] == _STATE_RECORD["conclusion"]


def test_an_unanswered_read_is_retried_once_and_each_miss_is_journaled(tmp_path: Path) -> None:
    """The first attempt gets no answer; the retry in the same evaluation reads it."""
    transport = _ScriptedTransport(results=[_no_answer(), _answered(payload=_STATE_RECORD)])
    journal = _Journal()

    payload = _reader(
        tmp_path=tmp_path, transport=transport, runner=_Runner(results=[]), journal=journal
    ).inspect_payload(factory="petri", run_id=_RUN_ID)

    assert len(transport.calls) == 2
    assert isinstance(payload, dict)
    assert payload["run_id"] == _RUN_ID
    assert [
        (r["stage"], r["factory"], r["run_id"], r["attempt"], r["elapsed_seconds"])
        for r in journal.records
    ] == [("acp-evidence-read-unanswered", "petri", _RUN_ID, 1, 12.5)]
    assert "TimeoutError" in str(journal.records[0]["error"])


def test_a_run_unanswered_on_every_attempt_is_unreadable_after_the_retry(tmp_path: Path) -> None:
    """Two misses report the run unreadable, journaled once per attempt."""
    transport = _ScriptedTransport(results=[_no_answer(), _no_answer()])
    runner = _Runner(results=[])
    journal = _Journal()

    payload = _reader(
        tmp_path=tmp_path, transport=transport, runner=runner, journal=journal
    ).inspect_payload(factory="petri", run_id=_RUN_ID)

    assert payload is None
    assert runner.calls == []
    assert [(r["attempt"], r["elapsed_seconds"]) for r in journal.records] == [
        (1, 12.5),
        (2, 12.5),
    ]


def test_a_server_that_refuses_the_route_falls_back_to_the_engine_cli(tmp_path: Path) -> None:
    """A build without the state route answers 404; the record still comes from inspect."""
    transport = _ScriptedTransport(results=[_answered(payload={"errors": []}, status=404)])
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout=json.dumps([{"run_id": _RUN_ID}]), stderr="")]
    )
    journal = _Journal()

    payload = _reader(
        tmp_path=tmp_path, transport=transport, runner=runner, journal=journal
    ).inspect_payload(factory="petri", run_id=_RUN_ID)

    assert payload == [{"run_id": _RUN_ID}]
    assert runner.calls == [["/factory/fabro", "inspect", _RUN_ID, "--json", "--server", _SERVER]]
    assert journal.records == []


@dataclass(kw_only=True)
class _ChunkedResponse:
    """A urlopen response that hands its body back in fixed chunks."""

    status: int
    chunks: list[bytes]
    headers: dict[str, str]

    def read(self, size: int = -1) -> bytes:
        _ = size
        return self.chunks.pop(0) if self.chunks else b""

    def __enter__(self) -> _ChunkedResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, traceback)


def test_the_transport_asks_for_gzip_and_decodes_a_compressed_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record arrives compressed and is read back as the JSON it encodes."""
    compressed = gzip.compress(json.dumps(_STATE_RECORD).encode("utf-8"))
    sent: list[urllib.request.Request] = []

    def _open(request: urllib.request.Request, timeout: float) -> _ChunkedResponse:
        _ = timeout
        sent.append(request)
        return _ChunkedResponse(
            status=200,
            chunks=[compressed[:100], compressed[100:]],
            headers={"Content-Encoding": "gzip"},
        )

    monkeypatch.setattr(urllib.request, "urlopen", _open)
    module = _module(name="_fabro_port_compressed")

    result = module.CompressedUrllibTransport().send(
        method="GET", url=_STATE_URL, headers={}, body=None, timeout_seconds=20.0
    )

    assert sent[0].get_header("Accept-encoding") == "gzip"
    assert (result.status, result.succeeded) == (200, True)
    assert json.loads(result.body) == _STATE_RECORD


def test_the_transport_abandons_a_body_that_outlasts_its_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-socket timeout never fires on a slow steady trickle; the whole read is bounded."""
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _ChunkedResponse(  # noqa: ARG005
            status=200, chunks=[b"{"] * 50, headers={}
        ),
    )
    module = _module(name="_fabro_port_compressed")

    result = module.CompressedUrllibTransport(clock=_Clock(step=1.0)).send(
        method="GET", url=_STATE_URL, headers={}, body=None, timeout_seconds=5.0
    )

    assert (result.status, result.succeeded) == (0, False)
    assert result.error is not None
    assert "TimeoutError" in result.error

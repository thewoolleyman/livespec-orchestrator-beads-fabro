"""Edge shapes of the compressed state read (bd-ib-fhmpik).

Beside `test_acp_factory_run_reader_state_read.py`, which pins the read itself:
these pin how a record that is already inspect-shaped, or carries no usable
checkpoint, is reshaped, that a reader with no journal still retries, and that
an uncompressed answer is read as it stands.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._fabro_port_compressed import (
    CompressedUrllibTransport,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult

_SERVER = "https://petri.example.ts.net:32276"
_RUN_ID = "01M6G8QJR80VH8T53MBGVEBP9E"


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


@dataclass(kw_only=True)
class _Transport:
    results: list[FabroHttpResult]
    calls: int = 0

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (method, url, headers, body, timeout_seconds)
        self.calls += 1
        return self.results.pop(0)


def _answered(*, record: object) -> FabroHttpResult:
    return FabroHttpResult(
        status=200, body=json.dumps(record), error=None, payload=None, succeeded=True
    )


def _read(*, tmp_path: Path, record: object) -> Any:
    reader = FactoryRunReader(
        repo=_repo(tmp_path=tmp_path),
        http_transport=_Transport(results=[_answered(record=record)]),
    )
    return reader.inspect_payload(factory="petri", run_id=_RUN_ID)


@pytest.mark.parametrize(
    ("record", "checkpoint"),
    [
        ({"status": {}, "checkpoint": {"current_node": "kept"}}, {"current_node": "kept"}),
        ({"status": {}, "checkpoints": []}, None),
        ({"status": {}, "checkpoints": ["not a mapping"]}, None),
    ],
)
def test_a_record_reshapes_only_from_a_usable_newest_checkpoint(
    tmp_path: Path, record: dict[str, object], checkpoint: object
) -> None:
    payload = _read(tmp_path=tmp_path, record=record)

    assert payload["run_id"] == _RUN_ID
    assert payload.get("checkpoint") == checkpoint


def test_a_reader_without_a_journal_still_retries_an_unanswered_read(tmp_path: Path) -> None:
    unanswered = FabroHttpResult(
        status=0, body="", error="TimeoutError: slow", payload=None, succeeded=False
    )
    transport = _Transport(results=[unanswered, unanswered])
    reader = FactoryRunReader(repo=_repo(tmp_path=tmp_path), http_transport=transport)

    assert reader.inspect_payload(factory="petri", run_id=_RUN_ID) is None
    assert transport.calls == 2


@dataclass(kw_only=True)
class _PlainResponse:
    body: bytes
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def read(self, size: int = -1) -> bytes:
        _ = size
        chunk, self.body = self.body, b""
        return chunk

    def __enter__(self) -> _PlainResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, traceback)


def test_an_uncompressed_answer_is_read_as_it_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _PlainResponse(body=b'{"status": {}}'),  # noqa: ARG005
    )

    result = CompressedUrllibTransport().send(
        method="GET",
        url=f"{_SERVER}/api/v1/runs/{_RUN_ID}/state",
        headers={},
        body=None,
        timeout_seconds=5.0,
    )

    assert (result.status, result.succeeded, result.body) == (200, True, '{"status": {}}')

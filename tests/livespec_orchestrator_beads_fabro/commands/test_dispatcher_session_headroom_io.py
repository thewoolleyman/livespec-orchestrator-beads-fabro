"""The bounded usage transport, and the gate this host resolves to.

Binds the transport half of the headroom clause of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": the exact projected credential snapshot, the finite
timeout, and the rule that missing, malformed, transport-failed and
authentication-failed readings are unobservable and never coerced to a number.

THE CONTROLS THAT CARRY THE WEIGHT:

- The REQUEST is asserted on its own — URL, method, bearer header and the
  timeout the call was made with — because a stub that answers whatever it is
  asked cannot tell a correct query from a plausible one, and a usage reading
  taken against the wrong endpoint or the wrong credential is exactly the
  clean-looking wrong answer the clause's "exact credential snapshot" wording
  exists to forbid.
- A 401 is its own unobservable result, NOT the transport one. Both are
  unobservable, so every assertion about skipping passes either way; only the
  reason token tells an operator to rotate rather than retry.
- `live_session_headroom_gate` answers `None` for an ABSENT token rather than
  an unobservable reading, because an unobservable reading would skip every
  covered candidate on a condition the dispatch path's own absent-credential
  refusal already reports with a remedy.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import credential_identity

_TOKEN = "sk-ant-oat01-usage-probe"
_NOW = "2026-10-14T12:00:00Z"


class _Response:
    """The minimal context-manager shape `urlopen` returns, as a double."""

    def __init__(self, *, status: int, body: bytes) -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def read(self, size: int) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _stub_urlopen(
    *, monkeypatch: pytest.MonkeyPatch, result: object, calls: list[dict[str, Any]]
) -> None:
    def _fake(request: Any, *, timeout: float) -> Any:
        calls.append({"request": request, "timeout": timeout})
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(headroom_io, "urlopen", _fake)


def _body(*, payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_the_request_names_the_usage_endpoint_and_the_projected_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The query is asserted, not just its answer."""
    calls: list[dict[str, Any]] = []
    _stub_urlopen(
        monkeypatch=monkeypatch,
        result=_Response(status=200, body=_body(payload={"five_hour": {"utilization": 12.5}})),
        calls=calls,
    )

    reading = headroom_io.read_claude_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert len(calls) == 1
    request = calls[0]["request"]
    assert request.full_url == headroom_io.CLAUDE_SESSION_USAGE_URL
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == f"Bearer {_TOKEN}"
    assert calls[0]["timeout"] == headroom_io.CLAUDE_SESSION_USAGE_TIMEOUT_SECONDS
    assert reading.utilization_percent == 12.5
    assert reading.remaining_headroom_percent == 87.5


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        pytest.param(
            HTTPError(url="u", code=401, msg="no", hdrs=None, fp=None),  # pyright: ignore[reportArgumentType]
            "authentication-failed",
            id="unauthorized",
        ),
        pytest.param(
            HTTPError(url="u", code=500, msg="no", hdrs=None, fp=None),  # pyright: ignore[reportArgumentType]
            "transport-failed",
            id="server-error",
        ),
        pytest.param(URLError(reason="refused"), "transport-failed", id="connection-refused"),
        pytest.param(TimeoutError("slow"), "transport-failed", id="timed-out"),
        pytest.param(_Response(status=204, body=b""), "transport-failed", id="non-ok-status"),
        pytest.param(_Response(status=200, body=b"not json"), "missing", id="undecodable-body"),
        pytest.param(
            _Response(status=200, body=_body(payload={"five_hour": "soon"})),
            "missing",
            id="window-not-an-object",
        ),
        pytest.param(
            _Response(status=200, body=_body(payload=["five_hour"])),
            "missing",
            id="body-not-an-object",
        ),
    ],
)
def test_every_transport_fault_is_an_explicit_unobservable_result(
    monkeypatch: pytest.MonkeyPatch, result: object, reason: str
) -> None:
    """A 401 names the credential; everything else names the transport.

    The identity is asserted on every row: a reading that never reached the
    provider still has to name the snapshot it was about, or a journal of
    unobservable readings cannot be attributed to a credential at all.
    """
    _stub_urlopen(monkeypatch=monkeypatch, result=result, calls=[])

    reading = headroom_io.read_claude_session_headroom(token=_TOKEN, observed_at=_NOW)

    assert reading.unobservable_reason == reason
    assert reading.utilization_percent is None
    assert reading.credential_identity == credential_identity(token=_TOKEN)
    assert reading.observed_at == _NOW


def test_an_absent_credential_resolves_no_gate_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No token is the absence of a SUBJECT, not an unobservable reading."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert headroom_io.live_session_headroom_gate(repo=tmp_path) is None


def test_the_live_gate_carries_this_repository_committed_floor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One reading plus the committed floor, as one value."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": '
        '{"dispatcher": {"session_headroom_floor_percent": 35}}}',
        encoding="utf-8",
    )
    _stub_urlopen(
        monkeypatch=monkeypatch,
        result=_Response(status=200, body=_body(payload={"five_hour": {"utilization": 90}})),
        calls=[],
    )

    gate = headroom_io.live_session_headroom_gate(repo=tmp_path)

    assert gate is not None
    assert gate.floor == 35
    assert gate.reading.remaining_headroom_percent == 10.0
    assert gate.skips_covered_candidates is True

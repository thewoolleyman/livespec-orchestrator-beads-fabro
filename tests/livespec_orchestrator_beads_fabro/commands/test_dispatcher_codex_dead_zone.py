"""Tests for the Codex credential renewal dead zone (bd-ib-i2odgf).

The dispatch freshness gate requires the host Codex access token to outlive the
run budget plus its margin (18000s). The guarded refresher spent a `codex exec`
request inside a six-minute guard. Between those two numbers lay an interval —
measured 2026-10-04 at `remaining_seconds` 13517 — in which every
Codex-projecting dispatch was refused while the sanctioned refresh declined to
act, and the refusal named a human `codex login`.

WHY RAISING THE GUARD ALONE CANNOT CLOSE IT, and why these tests assert an RPC
shape rather than a mock-advanced expiry. Upstream gates the ORDINARY refresh on
a five-minute window: `AuthManager::auth` refreshes only when
`should_refresh_proactively` holds, and that predicate is true only when the
access token expires within `CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES` (5)
(`codex-rs/login/src/auth/manager.rs`). A `codex exec` run with hours of
lifetime left therefore does NOT refresh — which is exactly why the guard was
sized at six minutes in the first place. A refresher that merely becomes
ELIGIBLE across the whole interval, while still spending a window-gated
`codex exec`, still cannot renew: it would attempt and decline.

The app-server `account/read` request is NOT window-gated. Its `refreshToken`
flag reaches `refresh_token_if_requested`, which calls
`AuthManager::refresh_token` with no expiry predicate at all
(`codex-rs/app-server/src/request_processors/account_processor.rs`), returning
early only for external-ChatGPT, API-key and personal-access-token auth — none
of which is the managed-auth posture the host holds. So the mechanism assertion
below is the load-bearing one: it can only pass against the route that is
capable of early renewal.

This module covers the DISPATCH half of the item. The ELIGIBILITY half — that no
remaining lifetime exists at which the freshness check refuses while the
refresher declines — is covered beside the status command in
`test_dispatcher_codex_refresh.py`, because the guard constant causes it.
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    CodexProjectionRefusal,
    project_codex_auth,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_NOW = 1_000_000

# The remaining lifetime measured on the host when dispatch of
# livespec-dev-tooling-74c65i was refused at stage run-config-overlay.
_MEASURED_DEAD_ZONE_REMAINING = 13_517

# The lifetime the dispatch freshness gate requires: run budget plus margin.
_REQUIRED_REMAINING = 18_000

# A ~10-day Codex access token, the lifetime the host mints at renewal.
_RENEWED_REMAINING = 864_000

# The renewal request is bounded at two minutes, so the clock can move by that
# much between the pre-request reading and the post-request grading.
_RENEWAL_ELAPSED = 120

_HOST_REFRESH_TOKEN = "host-refresh-token"

_RENEWAL_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal"
_RENEWAL_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_early_renewal.py"
)


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a fake Codex auth.json whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": _HOST_REFRESH_TOKEN,
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


class _AdvancingClock:
    """A clock that moves forward on every reading, modelling a slow request."""

    def __init__(self, *, start: int, step: int) -> None:
        self._now = start
        self._step = step
        self.readings: list[int] = []

    def __call__(self) -> int:
        self.readings.append(self._now)
        reading = self._now
        self._now += self._step
        return reading


class _StubOutcome:
    """A stand-in `CodexRenewalOutcome` with the two fields diagnostics read."""

    def __init__(self, *, answered: bool, detail: str) -> None:
        self.answered = answered
        self.detail = detail


class _RecordingAppServerRunner:
    """A Codex app-server runner that records the conversation it was handed."""

    def __init__(self, *, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[list[str], Path, list[str], float]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        request_lines: list[str],
        timeout_seconds: float,
    ) -> CommandResult:
        self.calls.append((argv, cwd, request_lines, timeout_seconds))
        return self.result


def _stub_renewal(
    *,
    monkeypatch: pytest.MonkeyPatch,
    answered: bool = True,
    detail: str = "the renewal request was answered",
) -> list[str]:
    """Stand in the bounded renewal, recording that it was spent exactly once."""
    spent: list[str] = []

    def renew() -> _StubOutcome:
        spent.append("requested")
        return _StubOutcome(answered=answered, detail=detail)

    monkeypatch.setattr(_dispatcher_codex_auth, "renew_host_codex_credential", renew, raising=False)
    return spent


def test_early_renewal_drives_the_ungated_account_read_rpc_not_a_gated_exec() -> None:
    """The renewal REQUESTS early refresh over the route capable of granting it.

    This is the mechanism assertion. `codex exec` cannot refresh a credential
    with hours of lifetime left (the five-minute `should_refresh_proactively`
    window), so a renewal spent on it would be a request that provably cannot
    advance the expiry. `account/read` with `refreshToken` is ungated.
    """
    assert _RENEWAL_MODULE_PATH.is_file()
    module = importlib.import_module(_RENEWAL_MODULE)

    argv = module.codex_app_server_argv()
    request_lines = module.codex_early_renewal_request_lines()

    # The app-server transport, never the window-gated one-shot `exec`.
    assert argv == ["codex", "app-server"]
    assert "exec" not in argv

    messages = [json.loads(line) for line in request_lines]
    # Newline-delimited JSON-RPC: no embedded newline may split a message.
    assert all("\n" not in line for line in request_lines)
    methods = [message["method"] for message in messages]
    assert methods == ["initialize", "initialized", "account/read"]
    # The handshake precedes the request, and `initialized` is a notification
    # (no id, and upstream serializes it with no `params` field at all).
    assert "id" in messages[0]
    assert "id" not in messages[1]
    assert "params" not in messages[1]
    # The one flag that makes this an EARLY renewal rather than a status read.
    assert messages[2]["params"] == {"refreshToken": True}
    assert messages[2]["id"] != messages[0]["id"]
    assert all(message["jsonrpc"] == "2.0" for message in messages)


def test_dead_zone_credential_is_admitted_once_the_credential_reads_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The projection re-reads after renewing, instead of carrying its verdict.

    The second read is a credential that HAS been renewed; the claim under test
    is that the projection honors the credential as it now stands rather than
    refusing on a lifetime it already superseded. That is the 2026-10-05
    observation in reverse: a session carried a stale blocker forward while the
    credential had become healthy.
    """
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + _MEASURED_DEAD_ZONE_REMAINING),
            _auth_json_with_exp(exp=_NOW + _RENEWED_REMAINING),
        )
    )
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: next(reads))
    spent = _stub_renewal(monkeypatch=monkeypatch)

    result = project_codex_auth(clock=_AdvancingClock(start=_NOW, step=_RENEWAL_ELAPSED))

    # Exactly one bounded renewal request, and the dispatch admitted after it.
    assert spent == ["requested"]
    assert isinstance(result, str)
    # The projected snapshot stays non-rotatable by the worker.
    assert _HOST_REFRESH_TOKEN not in result


def test_a_fresh_credential_is_admitted_without_spending_a_renewal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential already above the floor dispatches on one clock reading."""
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + _RENEWED_REMAINING),
    )
    spent = _stub_renewal(monkeypatch=monkeypatch)
    clock = _AdvancingClock(start=_NOW, step=_RENEWAL_ELAPSED)

    result = project_codex_auth(clock=clock)

    assert isinstance(result, str)
    assert spent == []
    assert clock.readings == [_NOW]


def test_the_renewed_credential_is_graded_against_the_post_request_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time spent inside the renewal is charged against the credential.

    The discriminator: this renewed credential clears the floor by 60 seconds
    at the PRE-request instant and misses it by 60 at the post-request instant.
    Re-grading against the stale pre-request timestamp would credit it with
    lifetime it no longer has and ADMIT a dispatch whose credential is already
    below the floor — an error in the unsafe direction, so it must refuse.
    """
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + _MEASURED_DEAD_ZONE_REMAINING),
            _auth_json_with_exp(exp=_NOW + _REQUIRED_REMAINING + 60),
        )
    )
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: next(reads))
    _ = _stub_renewal(monkeypatch=monkeypatch)
    clock = _AdvancingClock(start=_NOW, step=_RENEWAL_ELAPSED)

    result = project_codex_auth(clock=clock)

    # Two readings: one before the request, one after it. Never reused.
    assert clock.readings == [_NOW, _NOW + _RENEWAL_ELAPSED]
    assert isinstance(result, CodexProjectionRefusal)
    # The shortfall is reported against the LATER instant.
    assert str(_REQUIRED_REMAINING + 60 - _RENEWAL_ELAPSED) in result.message


def test_a_renewal_answered_but_unadvanced_refuses_without_claiming_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex answered and the expiry held: reported, but not as an auth verdict."""
    stale = _auth_json_with_exp(exp=_NOW + _MEASURED_DEAD_ZONE_REMAINING)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)
    _ = _stub_renewal(monkeypatch=monkeypatch, answered=True)

    result = project_codex_auth(clock=_AdvancingClock(start=_NOW, step=0))

    assert isinstance(result, CodexProjectionRefusal)
    message = result.message
    # Remaining versus required lifetime, both reported, no secrets.
    assert str(_MEASURED_DEAD_ZONE_REMAINING) in message
    assert str(_REQUIRED_REMAINING) in message
    assert _HOST_REFRESH_TOKEN not in message
    # The credential-source host is distinguished from the remote factory host.
    assert "credential-source" in message
    assert "factory host" in message
    # Bounded recovery and a fresh status read precede any human step.
    assert "codex-cred-status" in message
    assert message.index("codex-cred-refresh") < message.index("codex login")
    # It must not claim an authentication failure it has not measured.
    assert "does NOT by itself establish an authentication failure" in message
    assert "unrecoverable" not in message


def test_a_renewal_that_was_never_spent_says_so_and_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request that never reached Codex is no evidence about the credential.

    A missing executable and a declined refresh both leave the expiry
    unchanged, and only one of them says anything about the credential. The
    diagnostic must carry which happened; collapsing them is what turns an
    absent observation into a false demand for `codex login`.
    """
    stale = _auth_json_with_exp(exp=_NOW + _MEASURED_DEAD_ZONE_REMAINING)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)
    _ = _stub_renewal(
        monkeypatch=monkeypatch,
        answered=False,
        detail="codex app-server could not be started: codex",
    )

    result = project_codex_auth(clock=_AdvancingClock(start=_NOW, step=0))

    assert isinstance(result, CodexProjectionRefusal)
    message = result.message
    assert "could not be started" in message
    assert "never spent" in message
    assert "no evidence about this credential" in message


def test_missing_host_credential_refuses_without_spending_a_renewal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent credential genuinely needs a human; no request is spent on it."""
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: None)
    spent = _stub_renewal(monkeypatch=monkeypatch)

    result = project_codex_auth(clock=_AdvancingClock(start=_NOW, step=0))

    assert isinstance(result, CodexProjectionRefusal)
    assert spent == []
    assert "codex login" in result.message


def test_credential_unreadable_on_the_reread_refuses_on_the_measured_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential unreadable after renewal refuses on the pre-renewal reading."""
    reads = iter((_auth_json_with_exp(exp=_NOW + _MEASURED_DEAD_ZONE_REMAINING), None))
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: next(reads))
    _ = _stub_renewal(monkeypatch=monkeypatch)

    result = project_codex_auth(clock=_AdvancingClock(start=_NOW, step=_RENEWAL_ELAPSED))

    assert isinstance(result, CodexProjectionRefusal)
    assert str(_MEASURED_DEAD_ZONE_REMAINING) in result.message


def test_early_renewal_is_bounded_and_runs_on_the_credential_source_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """One bounded request, against the host's own Codex home, token untouched."""
    assert _RENEWAL_MODULE_PATH.is_file()
    module = importlib.import_module(_RENEWAL_MODULE)
    monkeypatch.chdir(tmp_path)
    runner = _RecordingAppServerRunner(result=CommandResult(exit_code=0, stdout="{}\n", stderr=""))

    result = module.request_early_codex_renewal(cwd=Path.cwd(), runner=runner)

    assert result.exit_code == 0
    assert len(runner.calls) == 1
    argv, cwd, request_lines, timeout_seconds = runner.calls[0]
    assert argv == module.codex_app_server_argv()
    assert cwd == Path.cwd()
    assert request_lines == module.codex_early_renewal_request_lines()
    assert timeout_seconds == module.CODEX_EARLY_RENEWAL_TIMEOUT_SECONDS
    # Bounded: a renewal that hung would hold the dispatch open indefinitely.
    assert 0 < module.CODEX_EARLY_RENEWAL_TIMEOUT_SECONDS <= 300
    # No token is copied or hand-edited; Codex rotates its own credential.
    assert not [line for line in request_lines if _HOST_REFRESH_TOKEN in line]


def test_renewal_outcomes_separate_an_answer_from_an_unspent_request() -> None:
    """The outcome classifier keeps the two unchanged-expiry reasons apart."""
    assert _RENEWAL_MODULE_PATH.is_file()
    module = importlib.import_module(_RENEWAL_MODULE)

    answered = module.classify_renewal_result(
        result=CommandResult(exit_code=0, stdout="{}\n", stderr="")
    )
    unspent = module.classify_renewal_result(
        result=CommandResult(
            exit_code=module.UNSPENDABLE_EXIT_CODE,
            stdout="",
            stderr="codex app-server could not be started: codex",
        )
    )
    odd_exit = module.classify_renewal_result(
        result=CommandResult(exit_code=3, stdout="", stderr="")
    )

    assert answered.answered is True
    assert unspent.answered is False
    assert "could not be started" in unspent.detail
    # An unspendable request with no stderr still carries a usable reason.
    bare = module.classify_renewal_result(
        result=CommandResult(exit_code=module.UNSPENDABLE_EXIT_CODE, stdout="", stderr="   ")
    )
    assert bare.detail
    assert odd_exit.answered is False
    assert "3" in odd_exit.detail

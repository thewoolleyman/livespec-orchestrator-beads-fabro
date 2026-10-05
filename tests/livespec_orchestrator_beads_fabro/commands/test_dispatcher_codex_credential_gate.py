"""The PRE-CLAIM Codex credential freshness gate (`bd-ib-tyqklx`).

`SPECIFICATION/scenarios.md` Scenario 19 requires the Dispatcher to refuse a
dispatch whose covered credential cannot outlive the run budget, and to surface
that the host credential needs renewal rather than projecting one that may
expire mid-run. The `credential-freshness-redesign` plan adds the POSITION that
refusal has to land in: before the selected item is claimed.

WHY THE POSITION IS THE WHOLE POINT. The decision used to run inside
`materialize_overlay`, which `dispatch_one` reaches only AFTER
`admit_and_select` has moved the item `ready -> active` and set its assignee. A
refusal there leaves an `active` row nobody is working, which is the stranded
shape the plan's own definition of done rules out. These tests therefore assert
on the ORDER of observable interactions -- what the gate did against what the
claim-and-launch surface recorded -- not merely on the exit code, because an
implementation that refused one step too late would produce the identical code.

THE REFUSAL TEXT IS ASSERTED HERE TOO, at the gate rather than at the
projection, for the reason the gate's own refusal spells out: an expiry that did
not advance and a renewal request that was never answered are not equivalent
evidence, and only one of them says anything at all about the credential.
Collapsing them is what turned an absent observation into a false demand for a
human `codex login` on 2026-10-05.
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth

_NOW = 1_000_000

# The host's own refresh token. It must never reach a journal record, which is
# what the projection's inert sentinel exists to guarantee one layer down.
_HOST_REFRESH_TOKEN = "host-refresh-token"

_GATE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate"
_GATE_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_credential_gate.py"
)

_ANSWERED_DETAIL = "the renewal request was answered by the host Codex app-server"
_UNANSWERED_DETAIL = "codex app-server could not be started: codex"


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a host Codex `auth.json` whose access-token JWT carries `exp`."""
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


class _StubOutcome:
    """A stand-in `CodexRenewalOutcome` carrying the two fields diagnostics read."""

    def __init__(self, *, answered: bool, detail: str) -> None:
        self.answered = answered
        self.detail = detail


class _RecordingJournal:
    """A journal that keeps what was appended instead of serializing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


def _stub_renewal(
    *,
    monkeypatch: pytest.MonkeyPatch,
    answered: bool,
    detail: str,
) -> list[str]:
    """Stand the bounded renewal in, recording every time it is spent.

    The hermetic tier must never spawn a real `codex app-server`, and the SPEND
    COUNT is an assertion in its own right: the gate is the one surface allowed
    to request a renewal, so a second request anywhere downstream would show up
    here as a second entry.
    """
    spent: list[str] = []

    def renew() -> _StubOutcome:
        spent.append("requested")
        return _StubOutcome(answered=answered, detail=detail)

    monkeypatch.setattr(_dispatcher_codex_auth, "renew_host_codex_credential", renew, raising=False)
    return spent


def test_the_gate_separates_an_unanswered_renewal_from_an_answered_unchanged_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two refusals over one credential, distinguished, neither an auth verdict.

    The discriminator is run in BOTH directions over the SAME stale credential,
    because a refusal that named the renewal observation in only one arm -- or
    that named it in neither -- would still refuse the dispatch and still look
    correct from the exit code.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    stale = _auth_json_with_exp(exp=_NOW - 10)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)

    answered_spend = _stub_renewal(monkeypatch=monkeypatch, answered=True, detail=_ANSWERED_DETAIL)
    answered = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",), clock=lambda: _NOW
    )
    unanswered_spend = _stub_renewal(
        monkeypatch=monkeypatch, answered=False, detail=_UNANSWERED_DETAIL
    )
    unanswered = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",), clock=lambda: _NOW
    )

    # Each arm refused, and each spent exactly ONE bounded renewal request.
    assert answered is not None
    assert unanswered is not None
    assert answered_spend == ["requested"]
    assert unanswered_spend == ["requested"]
    # Codex ANSWERED and the expiry held: reported as such, and the "no response
    # came back" note is absent, because here one did.
    assert _ANSWERED_DETAIL in answered
    assert "no successful renewal response was received" not in answered
    # No successful response came back: said so, and said that it is therefore
    # no evidence about this credential at all.
    assert _UNANSWERED_DETAIL in unanswered
    assert "no successful renewal response was received" in unanswered
    assert "no evidence about this credential" in unanswered
    # NEITHER observation is reported as an authentication failure, and neither
    # sends an operator to `codex login` off a non-advancing expiry.
    for message in (answered, unanswered):
        assert "does NOT by itself establish an authentication failure" in message
        assert "cannot report an authentication failure" in message
        assert "only if Codex explicitly reports an unrecoverable authentication" in message
        assert _HOST_REFRESH_TOKEN not in message


def test_the_gate_journals_its_refusal_naming_the_unclaimed_items_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The durable record of a pre-claim refusal, carrying no credential material.

    A refusal before claim leaves no `active` row and no run, so the journal is
    the only place the pass survives in. It names the items it declined to claim
    -- the audit question a reader actually has -- and the credential it graded
    reaches it in NO form: not the access token, not the refresh token.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    stale = _auth_json_with_exp(exp=_NOW - 10)
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", lambda: stale)
    _ = _stub_renewal(monkeypatch=monkeypatch, answered=True, detail=_ANSWERED_DETAIL)
    journal = _RecordingJournal()

    refusal = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx", "bd-ib-zz6gii"),
        clock=lambda: _NOW,
        journal=journal,
    )

    assert refusal is not None
    assert len(journal.records) == 1
    record = journal.records[0]
    assert record["stage"] == gate.CODEX_CREDENTIAL_GATE_STAGE
    assert record["unclaimed_work_item_ids"] == ["bd-ib-tyqklx", "bd-ib-zz6gii"]
    serialized = json.dumps(record, sort_keys=True)
    assert _HOST_REFRESH_TOKEN not in serialized
    assert "header." not in serialized


def test_a_credential_above_the_floor_admits_on_the_dispatcher_own_clock() -> None:
    """The ordinary pass: no refusal, no renewal, nothing journaled.

    This arm reads the host credential through the gate's OWN clock rather than
    an injected one, which is the only way the production reading is exercised
    at all -- every other test here hands a clock in. The autouse
    `_hermetic_codex_home` fixture supplies a far-future `exp`, so the grade is
    taken against the real clock exactly as a dispatch takes it.
    """
    assert _GATE_MODULE_PATH.is_file()
    gate = importlib.import_module(_GATE_MODULE)
    journal = _RecordingJournal()

    admitted = gate.codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-tyqklx",), journal=journal
    )

    assert admitted is None
    # Nothing is recorded for an admitted pass: the overlay writes its own
    # projection record, and a second line asserting admission would duplicate
    # it while making every healthy dispatch noisier to read.
    assert journal.records == []

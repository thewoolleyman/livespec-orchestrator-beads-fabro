"""Tests for the operator-facing Claude credential status command."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_claude_credential_command as command,
)
from livespec_orchestrator_beads_fabro.commands import (
    dispatcher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    selected_account_record_path,
)

_TEST_TOKEN = "test-oauth-token"
# The caam-published profile and the pool slot the credential wrapper injects for
# it, spelled literally the way an operator reading `printenv` sees them. The
# values are stand-ins bound to module locals so ruff's hardcoded-credential
# rules do not flag the literals, the same indirection the sibling
# slot-isolation module uses.
_SLOT_PROFILE = "anthropic-3"
_SLOT_ENV = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3"
_SLOT_TOKEN = "slot-oauth-token"
# The selector's own fallback marker. Matched rather than the whole line so the
# reason clause stays the selector's to word.
_FALLBACK_WARNING = "factory credential slot fallback"


def _status(*, usable: bool) -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition="usable" if usable else "exhausted",
        present=True,
        usable=usable,
        http_status=200 if usable else 429,
        error_type=None if usable else "rate_limit_error",
        input_tokens=9 if usable else None,
        output_tokens=1 if usable else None,
        message="CLAUDE_CODE_OAUTH_TOKEN is usable." if usable else "Capacity is exhausted.",
        remedy="No action required." if usable else "Wait before retrying.",
    )


def _status_for_token(*, token: str, usable: bool) -> ClaudeCredentialStatus:
    assert token == _TEST_TOKEN
    return _status(usable=usable)


def _recording_probe(*, seen: list[str]) -> Callable[..., ClaudeCredentialStatus]:
    """A usable probe recording every token it was handed, in order."""

    def probe(*, token: str) -> ClaudeCredentialStatus:
        seen.append(token)
        return _status(usable=True)

    return probe


def _publish_selected_profile(*, monkeypatch: pytest.MonkeyPatch, home: Path, profile: str) -> None:
    """Plant the caam selection record under a private HOME the selector reads.

    The path is composed through the selector's own
    `selected_account_record_path` rather than restated, so the fixture cannot
    drift from the location the product actually reads.
    """
    record = selected_account_record_path(home=home)
    record.parent.mkdir(parents=True, exist_ok=True)
    _ = record.write_text(json.dumps({"profile": profile}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))


def test_assess_distinguishes_absence_without_calling_probe() -> None:
    probe = MagicMock(return_value=_status(usable=True))

    status = command.assess_claude_credential(
        token=None,
        probe=probe,
        wrapper_text="['with-project-env.sh', '--']",
    )

    probe.assert_not_called()
    assert status.condition == "absent"
    assert status.present is False
    assert status.usable is False
    assert "CLAUDE_CODE_OAUTH_TOKEN" in status.message
    assert "with-project-env.sh" in status.remedy


def test_assess_passes_only_the_present_token_to_the_probe() -> None:
    calls: list[str] = []

    def recording_probe(*, token: str) -> ClaudeCredentialStatus:
        calls.append(token)
        return _status(usable=True)

    status = command.assess_claude_credential(
        token=_TEST_TOKEN,
        probe=recording_probe,
        wrapper_text="unused",
    )

    assert calls == [_TEST_TOKEN]
    assert status.usable is True


def test_status_json_reports_probe_bound_and_measured_usage(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)
    monkeypatch.setattr(
        command,
        "probe_claude_credential",
        lambda *, token: _status_for_token(token=token, usable=True),
    )

    exit_code = command.run_claude_cred_status(args=argparse.Namespace(as_json=True))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "condition": "usable",
        "credential_env": "CLAUDE_CODE_OAUTH_TOKEN",
        "error_type": None,
        "http_status": 200,
        "input_tokens": 9,
        "max_output_tokens": 1,
        "message": "CLAUDE_CODE_OAUTH_TOKEN is usable.",
        "model": "claude-haiku-4-5-20251001",
        "output_tokens": 1,
        "present": True,
        "probe_timeout_seconds": 20.0,
        "remedy": "No action required.",
        "usable": True,
    }


def test_status_human_refuses_an_exhausted_token(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)
    monkeypatch.setattr(
        command,
        "probe_claude_credential",
        lambda *, token: _status_for_token(token=token, usable=False),
    )

    exit_code = command.run_claude_cred_status(args=argparse.Namespace(as_json=False))

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "credential_env: CLAUDE_CODE_OAUTH_TOKEN" in out
    assert "present: true" in out
    assert "usable: false" in out
    assert "condition: exhausted" in out
    assert "http_status: 429" in out
    assert "error_type: rate_limit_error" in out
    assert "input_tokens: null" in out
    assert "remedy: Wait before retrying." in out


def test_status_probes_the_caam_selected_slot_not_the_unnumbered_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The probe reads the slot `select_factory_credential` resolves.

    Measured 2026-10-16 04:00Z-04:20Z (work-item bd-ib-6zfayy): this command
    reported the unnumbered token's anthropic-1 account as HTTP 429 while the
    published selection `CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3` read HTTP 200
    with about 88% five-hour headroom left, so every operator gate consulting
    it held for an account no dispatch was billing. Both variables are set
    here, with DISTINCT values: a probe handed the unnumbered one cannot be
    mistaken for a correct selection.
    """
    _publish_selected_profile(monkeypatch=monkeypatch, home=tmp_path, profile=_SLOT_PROFILE)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)
    monkeypatch.setenv(_SLOT_ENV, _SLOT_TOKEN)
    seen: list[str] = []
    monkeypatch.setattr(command, "probe_claude_credential", _recording_probe(seen=seen))

    exit_code = command.run_claude_cred_status(args=argparse.Namespace(as_json=True))

    assert exit_code == 0
    assert seen == [_SLOT_TOKEN]


@pytest.mark.parametrize(
    ("profile", "reason_fragment"),
    [
        (None, "no caam-published account selection record"),
        ("anthropic-9", "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_9"),
    ],
)
def test_status_falls_back_to_the_unnumbered_token_and_says_so_once_on_stderr(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: str | None,
    reason_fragment: str,
) -> None:
    """Both fallback arms probe the unnumbered token and announce themselves.

    The two arms are the selector's own: no published selection at all, and a
    published profile whose pool slot the wrapper did not inject. Each reports
    the reason that distinguishes it, because a fallback that said only that it
    fell back leaves an operator unable to tell a host with no rotation record
    from one whose wrapper is missing a slot — two conditions with different
    remedies. Exactly ONE line is required: a silent reversion to a different
    account is the defect, and a repeated one would mean the selector ran twice
    and the two runs could disagree.
    """
    if profile is None:
        monkeypatch.setenv("HOME", str(tmp_path))
    else:
        _publish_selected_profile(monkeypatch=monkeypatch, home=tmp_path, profile=profile)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)
    seen: list[str] = []
    monkeypatch.setattr(command, "probe_claude_credential", _recording_probe(seen=seen))

    exit_code = command.run_claude_cred_status(args=argparse.Namespace(as_json=True))

    assert exit_code == 0
    assert seen == [_TEST_TOKEN]
    announced = [line for line in capsys.readouterr().err.splitlines() if _FALLBACK_WARNING in line]
    assert len(announced) == 1
    assert reason_fragment in announced[0]


def test_status_names_the_env_var_it_actually_probed_in_both_renderings(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`credential_env` reports the probed variable, not a fixed constant.

    This is what makes the verdict attributable: a report that always named
    `CLAUDE_CODE_OAUTH_TOKEN` said nothing about which of several pool slots
    answered for it, so an operator reading HTTP 429 could not tell that the
    account being billed was a different one. Both renderings are asserted
    because the `--json` field and the human line are read by different
    consumers and each could drift alone.
    """
    _publish_selected_profile(monkeypatch=monkeypatch, home=tmp_path, profile=_SLOT_PROFILE)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TEST_TOKEN)
    monkeypatch.setenv(_SLOT_ENV, _SLOT_TOKEN)
    seen: list[str] = []
    monkeypatch.setattr(command, "probe_claude_credential", _recording_probe(seen=seen))

    assert command.run_claude_cred_status(args=argparse.Namespace(as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert command.run_claude_cred_status(args=argparse.Namespace(as_json=False)) == 0
    human = capsys.readouterr().out

    assert payload["credential_env"] == _SLOT_ENV
    assert f"credential_env: {_SLOT_ENV}" in human
    assert seen == [_SLOT_TOKEN, _SLOT_TOKEN]


def test_dispatcher_routes_claude_status_command(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    exit_code = dispatcher.main(argv=["claude-cred-status", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["credential_env"] == "CLAUDE_CODE_OAUTH_TOKEN"
    assert payload["condition"] == "absent"
    assert payload["present"] is False
    assert payload["usable"] is False

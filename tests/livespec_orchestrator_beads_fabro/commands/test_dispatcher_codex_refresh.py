"""Tests for the host Codex credential status alarm command."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

_NOW = 1_000_000
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_refresh.py"
)


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})


def test_codex_refresh_module_exists_with_expected_public_surface() -> None:
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )

    assert set(module.__all__) == {
        "CODEX_ALARM_THRESHOLD_SECONDS",
        "CODEX_REFRESH_GUARD_SECONDS",
        "HostCodexCredentialStatus",
        "assess_host_codex_credential",
    }
    assert module.CODEX_ALARM_THRESHOLD_SECONDS == 172_800
    assert module.CODEX_REFRESH_GUARD_SECONDS == 360


def test_missing_host_auth_alarms_and_names_codex_login() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )

    status = module.assess_host_codex_credential(
        source_auth_json=None,
        now_epoch=_NOW,
        alarm_threshold_seconds=172_800,
        refresh_guard_seconds=360,
    )

    assert status.present is False
    assert status.malformed is False
    assert status.expires_at_epoch is None
    assert status.remaining_seconds is None
    assert status.alarm is True
    assert status.refresh_due is False
    assert "codex login" in status.message


def test_malformed_host_auth_alarms_and_names_codex_login() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )

    status = module.assess_host_codex_credential(
        source_auth_json="{not-json",
        now_epoch=_NOW,
        alarm_threshold_seconds=172_800,
        refresh_guard_seconds=360,
    )

    assert status.present is True
    assert status.malformed is True
    assert status.expires_at_epoch is None
    assert status.remaining_seconds is None
    assert status.alarm is True
    assert status.refresh_due is False
    assert "present but unparseable" in status.message
    assert "codex login" in status.message


@given(
    remaining=st.integers(min_value=-86_400, max_value=604_800),
    alarm_threshold=st.integers(min_value=1, max_value=604_800),
    refresh_guard=st.integers(min_value=1, max_value=604_800),
)
def test_valid_host_auth_status_flags_match_thresholds(
    *,
    remaining: int,
    alarm_threshold: int,
    refresh_guard: int,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )
    exp = _NOW + remaining

    status = module.assess_host_codex_credential(
        source_auth_json=_auth_json_with_exp(exp=exp),
        now_epoch=_NOW,
        alarm_threshold_seconds=alarm_threshold,
        refresh_guard_seconds=refresh_guard,
    )

    assert status.present is True
    assert status.malformed is False
    assert status.expires_at_epoch == exp
    assert status.remaining_seconds == remaining
    assert status.alarm is (remaining < alarm_threshold)
    assert status.refresh_due is (remaining < refresh_guard)
    assert str(remaining) in status.message


def test_decode_codex_access_token_exp_is_public() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_projection"
    )

    assert "decode_codex_access_token_exp" in module.__all__
    assert (
        module.decode_codex_access_token_exp(source_auth_json=_auth_json_with_exp(exp=_NOW)) == _NOW
    )
    assert not hasattr(module, "_decode_codex_access_token_exp")


def test_run_codex_cred_status_json_payload(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    monkeypatch.setattr(
        codex_auth, "read_host_codex_auth", lambda: _auth_json_with_exp(exp=_NOW + 900)
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))

    exit_code = codex_auth.run_codex_cred_status(args=argparse.Namespace(as_json=True))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload == {
        "alarm": True,
        "expires_at_epoch": _NOW + 900,
        "expires_at_iso": "1970-01-12T14:01:40+00:00",
        "malformed": False,
        "message": "Host Codex credential expires in 900 seconds.",
        "present": True,
        "refresh_due": False,
        "remaining_days": pytest.approx(900 / 86_400),
        "remaining_seconds": 900,
    }


def test_dispatcher_routes_codex_cred_status_json(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    monkeypatch.setattr(codex_auth, "read_host_codex_auth", lambda: None)

    exit_code = dispatcher.main(argv=["codex-cred-status", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["present"] is False
    assert payload["alarm"] is True
    assert "codex login" in payload["message"]


def test_run_codex_cred_status_human_output(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    monkeypatch.setattr(
        codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + 200_000),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))

    exit_code = codex_auth.run_codex_cred_status(args=argparse.Namespace(as_json=False))

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "present: true" in out
    assert "alarm: false" in out
    assert "refresh_due: false" in out

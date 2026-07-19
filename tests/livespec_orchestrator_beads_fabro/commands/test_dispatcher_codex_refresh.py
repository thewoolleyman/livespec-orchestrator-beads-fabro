"""Tests for the host Codex credential status alarm command."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

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
        "classify_refresh_outcome",
        "should_invoke_codex_refresh",
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


@given(
    present=st.booleans(),
    malformed=st.booleans(),
    refresh_due=st.booleans(),
)
def test_should_invoke_codex_refresh_matches_present_well_formed_due_status(
    *,
    present: bool,
    malformed: bool,
    refresh_due: bool,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )
    status = module.HostCodexCredentialStatus(
        present=present,
        malformed=malformed,
        expires_at_epoch=_NOW + 10,
        remaining_seconds=10,
        alarm=refresh_due,
        refresh_due=refresh_due,
        message="status",
    )

    assert module.should_invoke_codex_refresh(status=status) is (
        present and not malformed and refresh_due
    )


@given(
    before_remaining=st.integers(min_value=-1_000, max_value=1_000),
    after_remaining=st.integers(min_value=-1_000, max_value=1_000),
    codex_ok=st.booleans(),
)
def test_classify_refresh_outcome_matches_guarded_refresh_state(
    *,
    before_remaining: int,
    after_remaining: int,
    codex_ok: bool,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )
    before = module.HostCodexCredentialStatus(
        present=True,
        malformed=False,
        expires_at_epoch=_NOW + before_remaining,
        remaining_seconds=before_remaining,
        alarm=True,
        refresh_due=before_remaining < 360,
        message="before",
    )
    after = module.HostCodexCredentialStatus(
        present=True,
        malformed=False,
        expires_at_epoch=_NOW + after_remaining,
        remaining_seconds=after_remaining,
        alarm=after_remaining < 172_800,
        refresh_due=after_remaining < 360,
        message="after",
    )

    outcome = module.classify_refresh_outcome(
        before=before,
        after=after,
        codex_ok=codex_ok,
    )

    if before_remaining >= 360:
        assert outcome == "noop-not-due"
    elif not codex_ok:
        assert outcome == "codex-error"
    elif after_remaining > before_remaining and after_remaining >= 360:
        assert outcome == "refreshed"
    else:
        assert outcome == "still-stale"


@pytest.mark.parametrize(
    ("present", "malformed"),
    [
        (False, False),
        (True, True),
    ],
)
def test_classify_refresh_outcome_treats_unrefreshable_status_as_still_stale(
    *,
    present: bool,
    malformed: bool,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )
    before = module.HostCodexCredentialStatus(
        present=present,
        malformed=malformed,
        expires_at_epoch=None,
        remaining_seconds=None,
        alarm=True,
        refresh_due=True,
        message="before",
    )

    outcome = module.classify_refresh_outcome(
        before=before,
        after=before,
        codex_ok=True,
    )

    assert outcome == "still-stale"


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


class _RecordingRunner:
    def __init__(self, *, result: CommandResult) -> None:
        self.result = result
        self.calls: list[tuple[list[str], Path, float, int | None]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert env is None
        self.calls.append((argv, cwd, timeout_seconds, stdin))
        return self.result


def test_run_codex_cred_refresh_not_due_skips_codex(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=0, stdout="OK\n", stderr=""))
    monkeypatch.setattr(
        codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + 3_600),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=True, dry_run=False)
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["outcome"] == "noop-not-due"
    assert payload["would_invoke_codex"] is False
    assert payload["invoked_codex"] is False


def test_run_codex_cred_refresh_due_invokes_codex_and_confirms_advanced_exp(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 86_400),
        )
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=0, stdout="OK\n", stderr=""))
    monkeypatch.setattr(codex_auth, "read_host_codex_auth", lambda: next(reads))
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=True, dry_run=False)
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["outcome"] == "refreshed"
    assert payload["would_invoke_codex"] is True
    assert payload["invoked_codex"] is True
    assert payload["before"]["remaining_seconds"] == 20
    assert payload["after"]["remaining_seconds"] == 86_400
    assert runner.calls == [
        (
            [
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "reply OK",
            ],
            Path.cwd(),
            120.0,
            subprocess.DEVNULL,
        )
    ]


def test_run_codex_cred_refresh_due_dry_run_never_invokes_codex(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=0, stdout="OK\n", stderr=""))
    monkeypatch.setattr(
        codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + 20),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=True, dry_run=True)
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["outcome"] == "still-stale"
    assert payload["dry_run"] is True
    assert payload["would_invoke_codex"] is True
    assert payload["invoked_codex"] is False


def test_run_codex_cred_refresh_codex_error_exits_one(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=1, stdout="", stderr="boom"))
    monkeypatch.setattr(
        codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + 20),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=False, dry_run=False)
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome: codex-error" in out
    assert "codex exec failed" in out


def test_run_codex_cred_refresh_malformed_auth_exits_one_without_codex(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=0, stdout="OK\n", stderr=""))
    monkeypatch.setattr(codex_auth, "read_host_codex_auth", lambda: "{")
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=True, dry_run=False)
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert runner.calls == []
    assert payload["outcome"] == "still-stale"
    assert payload["before"]["malformed"] is True


def test_dispatcher_routes_codex_cred_refresh_dry_run(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
    codex_auth = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )
    runner = _RecordingRunner(result=CommandResult(exit_code=0, stdout="OK\n", stderr=""))
    monkeypatch.setattr(
        codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_NOW + 20),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCommandRunner", lambda: runner)

    exit_code = dispatcher.main(argv=["codex-cred-refresh", "--json", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["dry_run"] is True
    assert payload["would_invoke_codex"] is True
    assert payload["outcome"] == "still-stale"

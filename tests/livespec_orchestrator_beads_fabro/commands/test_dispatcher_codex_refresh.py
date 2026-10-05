"""Tests for the host Codex credential status alarm command."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    assess_codex_credential_freshness,
    codex_freshness_required_seconds,
)

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
    # The guard is DERIVED from the dispatch freshness requirement rather than
    # written as its own number. The two diverging IS the dead zone: a guard
    # smaller than the requirement leaves an interval in which the freshness
    # gate refuses while the refresher declines to act.
    assert (
        codex_freshness_required_seconds(run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS)
        == module.CODEX_REFRESH_GUARD_SECONDS
    )
    assert module.CODEX_REFRESH_GUARD_SECONDS == 18_000


# Pinned at the boundary and at the measured incident, so these execute on
# every run rather than only when Hypothesis happens to generate them: the
# dead zone was an INTERVAL, and an interval is only proven closed at its edges.
@example(remaining=13_517)
@example(remaining=17_999)
@example(remaining=18_000)
@example(remaining=18_001)
@example(remaining=360)
@example(remaining=359)
@given(remaining=st.integers(min_value=-86_400, max_value=1_000_000))
def test_no_lifetime_refuses_dispatch_while_the_refresher_declines(*, remaining: int) -> None:
    """The eligibility contract is reconciled: the dead zone cannot exist.

    This is the item's defining property. Before the fix, every remaining
    lifetime between the 360-second guard and the 18000-second requirement
    refused dispatch while `should_invoke_codex_refresh` returned False —
    measured 2026-10-04 at 13517 seconds, where `refresh_due` was false and
    the refusal told a human to run `codex login`. Deriving the guard FROM the
    requirement makes that interval empty by construction, which is what this
    asserts over the whole range rather than at one point.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )
    source_auth_json = _auth_json_with_exp(exp=_NOW + remaining)

    verdict = assess_codex_credential_freshness(
        source_auth_json=source_auth_json,
        now_epoch=_NOW,
        run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    )
    status = module.assess_host_codex_credential(
        source_auth_json=source_auth_json,
        now_epoch=_NOW,
        alarm_threshold_seconds=module.CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=module.CODEX_REFRESH_GUARD_SECONDS,
    )

    if not verdict.fresh_enough:
        # Whenever dispatch would be refused, the sanctioned refresher is
        # eligible. A present, well-formed credential is never in a state
        # where the gate says no and the refresher says "not due".
        assert status.refresh_due is True
        assert module.should_invoke_codex_refresh(status=status) is True
    # And the converse, so the guard is not simply always-true: a credential
    # that clears the gate is not needlessly renewed on every timer tick.
    if verdict.fresh_enough:
        assert status.refresh_due is False
        assert module.should_invoke_codex_refresh(status=status) is False


def test_status_message_reports_remaining_against_the_required_lifetime() -> None:
    """An operator reads the shortfall off the message, not from arithmetic."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh"
    )

    status = module.assess_host_codex_credential(
        source_auth_json=_auth_json_with_exp(exp=_NOW + 13_517),
        now_epoch=_NOW,
        alarm_threshold_seconds=module.CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=module.CODEX_REFRESH_GUARD_SECONDS,
    )

    assert "13517" in status.message
    assert "18000" in status.message


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


# One pinned example per outcome branch, so every assert below executes on
# every run rather than only when Hypothesis happens to generate it: a fresh
# worktree has no example database, and the pre-push per-file coverage gate
# reported the still-stale assert unexecuted on a run CI had passed.
@example(before_remaining=400, after_remaining=0, codex_ok=True)
@example(before_remaining=100, after_remaining=0, codex_ok=False)
@example(before_remaining=100, after_remaining=500, codex_ok=True)
@example(before_remaining=100, after_remaining=50, codex_ok=True)
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
        # The message reports remaining versus REQUIRED lifetime, so an
        # operator can see the shortfall without computing it.
        "message": (
            "Host Codex credential expires in 900 seconds; renewal is due "
            "below 18000 seconds, which is the dispatch freshness requirement."
        ),
        "present": True,
        # 900 seconds is deep inside the dead zone the old 360-second guard
        # left open: the freshness gate refuses here, so renewal must be due.
        "refresh_due": True,
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
    """Records the app-server renewal conversation the refresher hands it."""

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
        # Above the reconciled 18000-second guard, so renewal is genuinely
        # not due; 3600 would now be inside it.
        lambda: _auth_json_with_exp(exp=_NOW + 100_000),
    )
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

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
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

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
    assert len(runner.calls) == 1
    argv, cwd, request_lines, timeout_seconds = runner.calls[0]
    # The ungated app-server route, with no sandbox-bypass flag of any kind.
    assert argv == ["codex", "app-server"]
    assert cwd == Path.cwd()
    assert timeout_seconds == 120.0
    assert json.loads(request_lines[-1])["params"] == {"refreshToken": True}


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
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

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
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

    exit_code = codex_auth.run_codex_cred_refresh(
        args=argparse.Namespace(as_json=False, dry_run=False)
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome: codex-error" in out
    assert "did not complete" in out


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
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

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
    monkeypatch.setattr(codex_auth, "ShellCodexAppServerRunner", lambda: runner)

    exit_code = dispatcher.main(argv=["codex-cred-refresh", "--json", "--dry-run"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert runner.calls == []
    assert payload["dry_run"] is True
    assert payload["would_invoke_codex"] is True
    assert payload["outcome"] == "still-stale"

"""Tests for the extracted guarded Codex refresh command body."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_NOW = 1_000_000


class _Runner:
    def __init__(self, *, result: CommandResult) -> None:
        self.result = result

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert argv == ["codex", "exec", "reply OK"]
        assert cwd == Path.cwd()
        assert timeout_seconds == 120.0
        assert env is None
        return self.result


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})


def test_refresh_command_module_public_surface() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )

    assert module.__all__ == ["run_codex_cred_refresh_with"]


def test_codex_error_without_stderr_stays_actionable(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=False, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json_with_exp(exp=_NOW + 20),
        runner_factory=lambda: _Runner(result=CommandResult(exit_code=1, stdout="", stderr="")),
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome: codex-error" in out
    assert "no stderr" in out


def test_successful_codex_call_without_exp_advance_exits_one(
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 20),
        )
    )

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=False, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: _Runner(result=CommandResult(exit_code=0, stdout="OK", stderr="")),
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome: still-stale" in out
    assert "run `codex login`" in out

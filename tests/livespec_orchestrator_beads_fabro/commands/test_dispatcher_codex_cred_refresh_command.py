"""Tests for the extracted guarded Codex refresh command body."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

_NOW = 1_000_000


class _Runner:
    def __init__(self, *, result: CommandResult, expected_argv: list[str] | None = None) -> None:
        self.result = result
        self.expected_argv = expected_argv or [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "reply OK",
        ]
        self.stdin: int | None = None

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        assert argv == self.expected_argv
        assert cwd == Path.cwd()
        assert timeout_seconds == 120.0
        assert env is None
        self.stdin = stdin
        return self.result


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})


def test_refresh_command_module_public_surface() -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )

    assert module.__all__ == ["run_codex_cred_refresh_with"]


def test_refresh_command_fails_closed_when_gate_hook_cannot_load(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = (
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None)
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 200_000),
        )
    )
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="OK", stderr=""),
        expected_argv=["codex", "exec", "reply OK"],
    )

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: runner,
    )

    assert exit_code == 0
    assert runner.stdin == subprocess.DEVNULL
    monkeypatch.undo()
    sys.modules.pop(module_name, None)
    importlib.import_module(module_name)


def test_refresh_command_fails_closed_when_gate_hook_execution_fails(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = (
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )

    class _FailingLoader:
        def create_module(self, spec: object) -> None:
            _ = spec

        def exec_module(self, module: object) -> None:
            _ = module
            raise RuntimeError("gate execution failed")

    spec = importlib.machinery.ModuleSpec("failing_codex_yolo_gate", _FailingLoader())
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: spec)
    sys.modules.pop(module_name, None)

    loaded = attempt(
        action=lambda: importlib.import_module(module_name),
        exceptions=(RuntimeError,),
    )
    assert not isinstance(loaded, AttemptFailure), loaded
    module = loaded
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 200_000),
        )
    )
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="OK", stderr=""),
        expected_argv=["codex", "exec", "reply OK"],
    )

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: runner,
    )

    assert exit_code == 0
    assert runner.stdin == subprocess.DEVNULL
    monkeypatch.undo()
    sys.modules.pop(module_name, None)
    importlib.import_module(module_name)


def test_refresh_command_uses_full_access_argv_and_devnull_when_gate_is_on(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 200_000),
        )
    )
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="OK", stderr=""),
        expected_argv=[
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "reply OK",
        ],
    )
    assert hasattr(module, "codex_yolo_gate")

    def gate_state(*, repo: Path) -> str:
        assert repo == Path.cwd()
        return "on"

    monkeypatch.setattr(module.codex_yolo_gate, "gate_state", gate_state)

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: runner,
    )

    assert exit_code == 0
    assert runner.stdin == subprocess.DEVNULL


def test_refresh_command_leaves_argv_as_is_when_gate_is_off(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 200_000),
        )
    )
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="OK", stderr=""),
        expected_argv=["codex", "exec", "reply OK"],
    )
    assert hasattr(module, "codex_yolo_gate")

    def gate_state(*, repo: Path) -> str:
        assert repo == Path.cwd()
        return "off"

    monkeypatch.setattr(module.codex_yolo_gate, "gate_state", gate_state)

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: runner,
    )

    assert exit_code == 0
    assert runner.stdin == subprocess.DEVNULL


def test_refresh_command_fails_closed_when_gate_state_raises(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command"
    )
    reads = iter(
        (
            _auth_json_with_exp(exp=_NOW + 20),
            _auth_json_with_exp(exp=_NOW + 200_000),
        )
    )
    runner = _Runner(
        result=CommandResult(exit_code=0, stdout="OK", stderr=""),
        expected_argv=["codex", "exec", "reply OK"],
    )

    def gate_state(*, repo: Path) -> str:
        assert repo == Path.cwd()
        raise RuntimeError("gate import drift")

    monkeypatch.setattr(module.codex_yolo_gate, "gate_state", gate_state)

    exit_code = module.run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=Path.cwd,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: next(reads),
        runner_factory=lambda: runner,
    )

    assert exit_code == 0
    assert runner.stdin == subprocess.DEVNULL


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

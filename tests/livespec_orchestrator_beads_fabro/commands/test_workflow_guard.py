"""Tests for the workflow_guard CLI supervisor."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from livespec_orchestrator_beads_fabro.commands import workflow_guard
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


@dataclass(frozen=True, kw_only=True)
class StubRunner:
    result: CommandResult

    def run(
        self,
        *,
        argv: list[str],
        cwd: object,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return self.result


def test_main_writes_success_to_stdout(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        workflow_guard,
        "ShellCommandRunner",
        lambda: StubRunner(result=CommandResult(exit_code=0, stdout="", stderr="")),
    )

    exit_code = workflow_guard.main(argv=["--repo", "."])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "No .github/workflows/ changes detected.\n"
    assert captured.err == ""


def test_main_writes_failure_to_stderr(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        workflow_guard,
        "ShellCommandRunner",
        lambda: StubRunner(
            result=CommandResult(
                exit_code=0,
                stdout=".github/workflows/ci.yml\n",
                stderr="",
            )
        ),
    )

    exit_code = workflow_guard.main(argv=["--repo", "."])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert ".github/workflows/ci.yml" in captured.err

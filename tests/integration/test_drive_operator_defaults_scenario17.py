"""Integration-tier acceptance for Scenario 17 drive operator-surface defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun, main


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def _ok(payload: object) -> CommandRun:
    return CommandRun(argv=("cmd",), returncode=0, stdout=json.dumps(payload), stderr="")


def test_omitted_repo_resolves_to_the_current_working_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = _Runner(results=[_ok([{"status": "green"}])])

    exit_code = main(argv=["--action", "impl:bd-ib-123"], runner=runner)

    assert exit_code == 0
    assert runner.calls[0][4] == str(tmp_path)
    assert "# drive" in capsys.readouterr().out


def test_explicit_repo_overrides_the_cwd_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    override = tmp_path / "override"
    override.mkdir()
    monkeypatch.chdir(cwd)
    runner = _Runner(results=[_ok([{"status": "green"}])])

    exit_code = main(argv=["--repo", str(override), "--action", "impl:bd-ib-123"], runner=runner)

    assert exit_code == 0
    assert runner.calls[0][4] == str(override)
    assert str(cwd) not in runner.calls[0]


def test_unresolvable_repo_is_a_precondition_error_naming_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"

    exit_code = main(argv=["--repo", str(missing), "--action", "impl:bd-ib-123", "--json"])

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "ERROR: --repo does not exist:" in err
    assert str(missing) in err


def test_markdown_is_default_and_json_is_explicit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    exit_code = main(
        argv=["--repo", str(repo), "--action", "impl:bd-ib-123"],
        runner=_Runner(results=[_ok([{"status": "green"}])]),
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.lstrip().startswith("#")
    assert "status: **green**" in out

    exit_code = main(
        argv=["--repo", str(repo), "--action", "impl:bd-ib-123", "--json"],
        runner=_Runner(results=[_ok([{"status": "green"}])]),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "green"

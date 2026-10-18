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


def _dispatcher_repo(*, argv: tuple[str, ...]) -> str:
    """The target repository the recorded dispatcher argv names.

    Read by POSITION RELATIVE TO `--repo` rather than at a fixed index,
    because the argv `drive` builds is VARIABLE-LENGTH: an asserted invoker
    identity is forwarded as its own `--invoker <id>` pair ahead of `--repo`,
    so every element after it moves by two. A fixed index therefore reads the
    repository only on a host that asserted no identity — and the index read
    this replaces returned the INVOKER IDENTITY instead on every dispatching
    session, which the driver's own gate requires to export
    `LIVESPEC_INVOKER`. Measured 2026-10-18: both cases below failed host-side
    pre-push on a tree whose default-branch continuous integration was green,
    because continuous integration exports no identity (work-item
    bd-ib-untu6x).
    """
    return argv[argv.index("--repo") + 1]


def test_omitted_repo_resolves_to_the_current_working_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = _Runner(results=[_ok([{"status": "green"}])])

    exit_code = main(argv=["--action", "impl:bd-ib-123"], runner=runner)

    assert exit_code == 0
    assert _dispatcher_repo(argv=runner.calls[0]) == str(tmp_path)
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
    assert _dispatcher_repo(argv=runner.calls[0]) == str(override)
    assert str(cwd) not in runner.calls[0]


def test_an_asserted_invoker_shifts_the_argv_without_moving_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the lookup above — the one case whose argv is shifted.

    `tests/conftest.py` removes `LIVESPEC_INVOKER` before every test, so no
    other case in this module reaches the longer argv and a FIXED-INDEX read
    would satisfy all of them. This case sets the identity explicitly, exactly
    as that fixture's contract requires, and asserts both halves the shift
    turns on: the identity really is forwarded AHEAD of `--repo`, which is
    what puts something other than the repository at index 4, and the
    repository is still found anyway.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_INVOKER", "claude:test")
    runner = _Runner(results=[_ok([{"status": "green"}])])

    exit_code = main(argv=["--action", "impl:bd-ib-123"], runner=runner)

    assert exit_code == 0
    argv = runner.calls[0]
    assert argv.index("--invoker") < argv.index("--repo")
    assert argv[argv.index("--invoker") + 1] == "claude:test"
    assert argv[4] != str(tmp_path)
    assert _dispatcher_repo(argv=argv) == str(tmp_path)


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

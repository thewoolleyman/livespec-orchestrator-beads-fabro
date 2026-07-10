"""Tests for the drive operator executor surface."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun, build_dispatcher_argv


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def test_build_dispatcher_argv_uses_shadow_loop_for_selected_impl_item(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dispatcher_bin = tmp_path / "dispatcher.py"

    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=dispatcher_bin,
        work_item_ref="bd-ib-123",
    )

    assert argv == (
        "python3",
        str(dispatcher_bin),
        "loop",
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--mode",
        "shadow",
        "--item",
        "bd-ib-123",
        "--json",
    )


def test_drive_rejects_retired_spec_action_handoffs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[])

    result = drive.run_action(repo=repo, action_id="spec:revise:0", runner=runner)

    assert result["status"] == "failed"
    assert result["kind"] == "unknown"
    assert "spec:<action>:<index>" not in result["summary"]
    assert runner.calls == []


def test_drive_has_no_plan_entry_point(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        drive.main(argv=["plan", "--repo", str(repo), "--json"])

    assert exc_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err

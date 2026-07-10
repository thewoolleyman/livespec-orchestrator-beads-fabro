"""Scenario 42 integration coverage for list-plan-threads."""

import json

import pytest
from livespec_orchestrator_beads_fabro.commands.list_plan_threads import main


def test_scenario42_list_plan_threads_enumerates_unarchived_plan_threads(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "plan"
    _ = (plan / "beta-topic").mkdir(parents=True)
    _ = (plan / "alpha-topic").mkdir()
    _ = (plan / "archive" / "old-topic").mkdir(parents=True)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    rc = main(argv=["--json", "--project-root", str(tmp_path)])

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {"plan_threads": ["alpha-topic", "beta-topic"]}
    assert "old-topic" not in captured.out
    assert "plan/archive" not in captured.out
    assert after == before


def test_scenario42_missing_plan_directory_exits_zero(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(argv=["--json", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {"plan_threads": []}

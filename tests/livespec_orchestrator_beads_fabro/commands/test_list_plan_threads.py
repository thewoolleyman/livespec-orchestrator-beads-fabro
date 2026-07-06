"""Scenario 42 coverage for the list-plan-threads thin-transport command."""

import json

import pytest
from livespec_orchestrator_beads_fabro.commands.list_plan_threads import (
    list_plan_threads,
    main,
)


def test_scenario42_json_lists_unarchived_threads_in_lexicographic_order(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "plan"
    _ = (plan / "beta-topic").mkdir(parents=True)
    _ = (plan / "alpha-topic").mkdir()
    _ = (plan / "archive" / "old-topic").mkdir(parents=True)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    rc = main(["--json", "--project-root", str(tmp_path)])

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {"plan_threads": ["alpha-topic", "beta-topic"]}
    assert "old-topic" not in captured.out
    assert "plan/archive" not in captured.out
    assert after == before


def test_scenario42_missing_plan_directory_degrades_to_empty_json(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--json", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {"plan_threads": []}


def test_human_output_emits_one_topic_per_line(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "plan"
    _ = (plan / "beta-topic").mkdir(parents=True)
    _ = (plan / "alpha-topic").mkdir()

    rc = main(["--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == "alpha-topic\nbeta-topic\n"


def test_list_plan_threads_ignores_files_and_archive_directory(tmp_path) -> None:
    plan = tmp_path / "plan"
    _ = (plan / "topic").mkdir(parents=True)
    (plan / "notes.md").write_text("not a thread\n", encoding="utf-8")
    _ = (plan / "archive").mkdir()

    assert list_plan_threads(project_root=tmp_path) == ["topic"]

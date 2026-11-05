"""The read-only conflict measurement behind Scenario 184's resume arm."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    measure_conflicted_paths,
    record_file_resume_paths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_DECLARATION = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "record_files": [{"path": "record.json"}, {"path": "notes.md"}]
    }
  }
}"""


@dataclass(kw_only=True)
class _Runner:
    """A command seam that makes the measurement's Git invocation observable."""

    result: CommandResult
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, env)
        assert timeout_seconds == 30.0
        self.calls.append(argv)
        return self.result


def test_measurement_returns_each_conflicted_path_from_git_merge_tree(tmp_path: Path) -> None:
    runner = _Runner(result=CommandResult(exit_code=1, stdout="record.json\nnotes.md\n", stderr=""))

    measurement = measure_conflicted_paths(
        repo=tmp_path,
        runner=runner,
        pr_head="head1111",
        default_branch_tip="base2222",
    )

    assert measurement.paths == ("record.json", "notes.md")
    assert measurement.failure is None
    assert runner.calls == [
        ["git", "merge-tree", "--write-tree", "--name-only", "head1111", "base2222"]
    ]


@pytest.mark.parametrize(
    ("result", "failure"),
    [
        (
            CommandResult(exit_code=0, stdout="", stderr="unable to compare\n"),
            "unable to compare",
        ),
        (
            CommandResult(exit_code=None, stdout=None, stderr=None),
            "git merge-tree exited None",
        ),
        (
            CommandResult(exit_code=1, stdout="", stderr=""),
            "git merge-tree named no conflicted paths",
        ),
    ],
)
def test_measurement_names_its_failure_when_it_cannot_produce_a_path_set(
    tmp_path: Path, result: CommandResult, failure: str
) -> None:
    measurement = measure_conflicted_paths(
        repo=tmp_path,
        runner=_Runner(result=result),
        pr_head="head1111",
        default_branch_tip="base2222",
    )

    assert measurement.paths is None
    assert measurement.failure == failure


def test_only_a_nonempty_conflict_set_wholly_declared_as_record_files_is_eligible() -> None:
    assert record_file_resume_paths(
        config_text=_DECLARATION,
        conflicted_paths=("record.json", "notes.md"),
    ) == ("record.json", "notes.md")
    assert (
        record_file_resume_paths(
            config_text=_DECLARATION,
            conflicted_paths=("record.json", "foreign.py"),
        )
        is None
    )
    assert record_file_resume_paths(config_text=_DECLARATION, conflicted_paths=()) is None


@pytest.mark.parametrize(
    "config_text",
    [
        "not json",
        "[]",
        "{}",
        '{"livespec-orchestrator-beads-fabro": []}',
        '{"livespec-orchestrator-beads-fabro": {}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": []}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": {}}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": []}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [null]}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{}]}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{"path": ""}]}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{"path": 3}]}}}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{"path": "a"}, {"path": "a"}]}}}',
    ],
)
def test_unreadable_or_ambiguous_record_file_declarations_never_admit_resume(
    config_text: str,
) -> None:
    assert (
        record_file_resume_paths(config_text=config_text, conflicted_paths=("record.json",)) is None
    )

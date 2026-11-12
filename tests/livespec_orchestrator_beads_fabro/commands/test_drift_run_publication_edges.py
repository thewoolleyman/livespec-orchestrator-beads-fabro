"""Failure and malformed-input coverage for drift-run pull-request publication."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._drift_run_publication"


@dataclass(kw_only=True)
class _Runner:
    """Return configured results while retaining the command sequence."""

    results: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return self.results.pop(0)


def _module() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


@pytest.mark.parametrize(
    "result",
    [
        CommandResult(exit_code=1, stdout="", stderr="unavailable"),
        CommandResult(exit_code=0, stdout="not-json", stderr=""),
        CommandResult(exit_code=0, stdout="{}", stderr=""),
        CommandResult(
            exit_code=0, stdout='["not-a-record", {"body": 2}, {"body": "ordinary"}]', stderr=""
        ),
    ],
)
def test_an_unreadable_or_malformed_open_pull_request_listing_files_nothing(
    tmp_path: Path, result: CommandResult
) -> None:
    module = _module()

    assert (
        module.open_drift_run_proposals(repo=tmp_path, runner=_Runner(results=[result]))
        == frozenset()
    )


@pytest.mark.parametrize("failed_command", range(4))
def test_a_failed_publication_command_does_not_report_a_durable_filing(
    tmp_path: Path, failed_command: int
) -> None:
    module = _module()
    worktree = tmp_path / "worktree"
    proposals = worktree / "SPECIFICATION" / "proposed_changes"
    proposals.mkdir(parents=True)
    _ = (proposals / "drift-one.md").write_text(
        "---\nfinding_identity: drift-one\n---\nproposal\n", encoding="utf-8"
    )
    results = [CommandResult(exit_code=0, stdout="", stderr="") for _ in range(failed_command)]
    results.append(CommandResult(exit_code=1, stdout="", stderr="refused"))
    runner = _Runner(results=results)

    assert (
        module.publish_drift_proposals(
            repo=tmp_path,
            worktree=worktree,
            branch="spec/drift-one",
            default_branch="master",
            runner=runner,
        )
        is False
    )
    assert len(runner.calls) == failed_command + 1


def test_only_valid_front_matter_identities_are_carried_to_the_pull_request_body(
    tmp_path: Path,
) -> None:
    module = _module()
    worktree = tmp_path / "worktree"
    proposals = worktree / "SPECIFICATION" / "proposed_changes"
    proposals.mkdir(parents=True)
    _ = (proposals / "valid.md").write_text(
        "---\nfinding_identity: drift-one\n---\nproposal\n", encoding="utf-8"
    )
    _ = (proposals / "quoted.md").write_text(
        "proposal\nfinding_identity: not-metadata\n", encoding="utf-8"
    )
    _ = (proposals / "unclosed.md").write_text("---\nfinding_identity: lost\n", encoding="utf-8")
    _ = (proposals / "empty.md").write_text("", encoding="utf-8")
    (proposals / "directory.md").mkdir()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="", stderr="") for _ in range(4)])

    assert module.publish_drift_proposals(
        repo=tmp_path,
        worktree=worktree,
        branch="spec/drift-one",
        default_branch="master",
        runner=runner,
    )
    body = runner.calls[-1][-1]
    assert "- drift-one" in body
    assert "not-metadata" not in body
    assert "lost" not in body


def test_an_empty_worktree_uses_the_human_readable_pull_request_body(tmp_path: Path) -> None:
    module = _module()
    worktree = tmp_path / "worktree"
    (worktree / "SPECIFICATION" / "proposed_changes").mkdir(parents=True)
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="", stderr="") for _ in range(4)])

    assert module.publish_drift_proposals(
        repo=tmp_path,
        worktree=worktree,
        branch="spec/drift-empty",
        default_branch="master",
        runner=runner,
    )
    assert runner.calls[-1][-1] == "Drift-origin proposals filed by the Dispatcher drift job."


def test_an_empty_identity_line_on_an_open_drift_pull_request_is_ignored(tmp_path: Path) -> None:
    module = _module()
    runner = _Runner(
        results=[
            CommandResult(
                exit_code=0,
                stdout='[{"body": "Finding identities:\\n- "}]',
                stderr="",
            )
        ]
    )

    assert module.open_drift_run_proposals(repo=tmp_path, runner=runner) == frozenset()

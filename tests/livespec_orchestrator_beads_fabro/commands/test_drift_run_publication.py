"""The drift job publishes proposals from an isolated worktree."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._drift_run_publication"
_MODULE_PATH = _COMMANDS / "_drift_run_publication.py"


@dataclass(kw_only=True)
class _Runner:
    """Records the forge writes a successful publication must make."""

    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = timeout_seconds
        self.calls.append((argv, cwd))
        return CommandResult(exit_code=0, stdout="https://example.test/pr/1\n", stderr="")


def _publication() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


def test_a_drift_proposal_is_committed_and_opened_from_its_worktree(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    publication = _publication()
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    proposal = worktree / "SPECIFICATION" / "proposed_changes" / "drift-one.md"
    proposal.parent.mkdir(parents=True)
    _ = proposal.write_text("proposal\n", encoding="utf-8")
    runner = _Runner()

    published = publication.publish_drift_proposals(
        repo=primary,
        worktree=worktree,
        branch="spec/drift-run-one",
        default_branch="master",
        runner=runner,
    )

    assert published is True
    assert runner.calls == [
        (["git", "add", "SPECIFICATION/proposed_changes"], worktree),
        (["git", "commit", "-m", "docs(spec): file drift proposals"], worktree),
        (["git", "push", "origin", "HEAD:spec/drift-run-one"], worktree),
        (
            [
                "gh",
                "pr",
                "create",
                "--base",
                "master",
                "--head",
                "spec/drift-run-one",
                "--title",
                "docs(spec): file drift proposals",
                "--body",
                "Drift-origin proposals filed by the Dispatcher drift job.",
            ],
            worktree,
        ),
    ]
    assert list(primary.rglob("drift-one.md")) == []


def test_open_drift_run_pull_requests_supply_filed_identities_and_queue_count(
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    publication = _publication()
    marker = publication.drift_pull_request_body(finding_identities=("drift-one", "drift-two"))

    @dataclass(kw_only=True)
    class _ListRunner:
        calls: list[tuple[list[str], Path]] = field(default_factory=list)

        def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
            _ = timeout_seconds
            self.calls.append((argv, cwd))
            return CommandResult(
                exit_code=0,
                stdout=json.dumps([{"body": marker}, {"body": "ordinary pull request"}]),
                stderr="",
            )

    runner = _ListRunner()

    open_proposals = publication.open_drift_run_proposals(repo=tmp_path, runner=runner)

    assert open_proposals == frozenset({"drift-one", "drift-two"})
    assert runner.calls == [
        (
            ["gh", "pr", "list", "--state", "open", "--json", "body", "--limit", "100"],
            tmp_path,
        )
    ]

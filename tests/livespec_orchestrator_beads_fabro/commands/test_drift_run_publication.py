"""The drift job publishes its proposals from an isolated worktree."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_PATH = _COMMANDS / "_drift_run_publication.py"


@dataclass(kw_only=True)
class _RecordingRunner:
    """A forge and git seam that records the isolated publication sequence."""

    argvs: list[list[str]] = field(default_factory=list)
    written_documents: dict[str, str] = field(default_factory=dict)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[:3] == ["git", "worktree", "remove"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:2] == ["git", "commit"]:
            proposal = cwd / "SPECIFICATION" / "proposed_changes" / "drift-one.md"
            self.written_documents[str(proposal)] = proposal.read_text(encoding="utf-8")
        if argv[:3] == ["gh", "pr", "create"]:
            return CommandResult(exit_code=0, stdout="https://example.invalid/pr/1\n", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_a_drift_job_publishes_one_pull_request_from_a_fresh_worktree(tmp_path: Path) -> None:
    """The primary checkout is never the proposal-writing venue."""
    assert _MODULE_PATH.is_file()

    publication = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run_publication"
    )

    runner = _RecordingRunner()
    result = publication.GitDriftRunPublisher(runner=runner).publish(
        repo=tmp_path,
        default_branch="master",
        proposals=(publication.DriftProposal(identity="drift-one", document="proposal body\n"),),
    )

    assert result.filed == ("drift-one",)
    assert not (tmp_path / "SPECIFICATION" / "proposed_changes").exists()
    assert len(runner.written_documents) == 1
    assert tuple(runner.written_documents.values()) == ("proposal body\n",)
    assert ["git", "fetch", "origin", "master"] in runner.argvs
    assert sum(argv[:3] == ["gh", "pr", "create"] for argv in runner.argvs) == 1

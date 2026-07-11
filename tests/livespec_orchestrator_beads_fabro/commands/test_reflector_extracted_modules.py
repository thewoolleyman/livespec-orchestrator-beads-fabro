from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _reflector_runtime as runtime
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import (
    GitPrLessonsProposer,
    LessonProposal,
)


def test_runtime_resolve_claude_path_covers_override_and_found_binary(
    monkeypatch,
) -> None:
    assert (
        runtime.resolve_claude_path(environ={"LIVESPEC_REFLECTOR_CLAUDE_PATH": "/opt/claude"})
        == "/opt/claude"
    )
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/usr/bin/claude")
    assert runtime.resolve_claude_path(environ={}) == "/usr/bin/claude"


def test_runtime_resolve_claude_path_covers_local_bin_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)
    fake_claude = tmp_path / "claude"
    _ = fake_claude.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "_CLAUDE_LOCAL_BIN_FALLBACK", str(fake_claude))
    assert runtime.resolve_claude_path(environ={}) == str(fake_claude)


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="https://example.invalid/pr/1\n", stderr="")


def test_git_pr_lessons_proposer_uses_stable_normalized_branch_slug(tmp_path: Path) -> None:
    lessons = tmp_path / "loop-reflection-gate" / "lessons.md"
    lessons.parent.mkdir(parents=True)
    _ = lessons.write_text("", encoding="utf-8")
    first = _RecordingRunner()
    second = _RecordingRunner()
    proposal_a = LessonProposal(title="t", body="Body   Text")
    proposal_b = LessonProposal(title="t", body="body text")

    _ = GitPrLessonsProposer(runner=first).propose(proposal=proposal_a, repo=tmp_path)
    _ = GitPrLessonsProposer(runner=second).propose(proposal=proposal_b, repo=tmp_path)

    assert first.calls[0][-1] == second.calls[0][-1]
    assert first.calls[0][-1].startswith("reflector-lesson-")
    assert len(first.calls[0][-1].removeprefix("reflector-lesson-")) == 12

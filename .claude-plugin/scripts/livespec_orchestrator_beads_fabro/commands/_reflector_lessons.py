"""Lesson proposal seams for the out-of-band reflector."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub

__all__: list[str] = [
    "GitPrLessonsProposer",
    "LessonProposal",
    "LessonsProposer",
    "RecordingLessonsProposer",
]

_CLAUDE_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, kw_only=True)
class LessonProposal:
    """A proposed Reflexion-style lesson, opened as a PR for human ratify."""

    title: str
    body: str


class LessonsProposer(Protocol):
    """Seam for proposing a lesson by opening a PR that edits `lessons.md`."""

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        """Open a PR proposing the lesson; return the PR URL/ref or None."""
        ...


@dataclass(kw_only=True)
class RecordingLessonsProposer:
    """Test-double `LessonsProposer`: records proposals, opens no real PR."""

    proposals: list[LessonProposal] = field(default_factory=list)
    pr_ref: str | None = "https://example.invalid/pr/0"

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        _ = repo
        self.proposals.append(proposal)
        return self.pr_ref


@dataclass(kw_only=True)
class GitPrLessonsProposer:
    """Production `LessonsProposer`: branch + commit + push + `gh pr create`."""

    runner: CommandRunner
    lessons_path: Path = Path("loop-reflection-gate/lessons.md")
    branch_prefix: str = "reflector-lesson"

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        return self._propose_impl(proposal=proposal, repo=repo)  # pragma: no cover

    def _propose_impl(  # pragma: no cover
        self, *, proposal: LessonProposal, repo: Path
    ) -> str | None:
        slug = _lesson_slug(title=proposal.title, repo=repo, body=proposal.body)
        branch = f"{self.branch_prefix}-{slug}"
        target = repo / self.lessons_path
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        scrubbed = scrub(value=proposal.body)
        _ = target.write_text(existing + "\n" + scrubbed + "\n", encoding="utf-8")
        steps: list[list[str]] = [
            ["git", "-C", str(repo), "checkout", "-b", branch],
            ["git", "-C", str(repo), "add", str(self.lessons_path)],
            ["git", "-C", str(repo), "commit", "-m", f"docs(lessons): {proposal.title}"],
            ["git", "-C", str(repo), "push", "-u", "origin", branch],
        ]
        for argv in steps:
            result = self.runner.run(argv=argv, cwd=repo, timeout_seconds=_CLAUDE_TIMEOUT_SECONDS)
            if result.exit_code != 0:
                return None
        pr = self.runner.run(
            argv=["gh", "pr", "create", "--fill", "--head", branch],
            cwd=repo,
            timeout_seconds=_CLAUDE_TIMEOUT_SECONDS,
        )
        return pr.stdout.strip() if pr.exit_code == 0 else None


def _lesson_slug(*, title: str, repo: Path, body: str) -> str:
    material = f"{title}||{repo}||{' '.join(body.lower().split())}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

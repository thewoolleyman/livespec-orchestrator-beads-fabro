"""Scenario 199 requires the re-entered-stage checkpoint-folding instruction."""

from __future__ import annotations

from pathlib import Path

_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
)


def test_fix_stages_direct_the_runner_amend_over_open_red_checkpoints() -> None:
    """Both re-entered fix stages prohibit hand rewrites before the runner amend."""
    for name in ("fix.md", "review-fix.md"):
        text = (_PROMPTS / name).read_text(encoding="utf-8")

        assert "sandbox commit\nrunner (`git commit --amend --no-edit`" in text
        assert "folds engine checkpoint commits sitting above the open Red onto it before" in text
        assert "issue that runner amend while HEAD is on the checkpoints" in text
        assert "run `git reset` with either `--soft` or `--hard`" in text
        assert "do not otherwise rewrite\nthe open Red or the checkpoints above it" in text

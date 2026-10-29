"""The Definition-of-Done gate prompt grades the marked section, never a quoted comment."""

from __future__ import annotations

from pathlib import Path

_PROMPT = (
    Path(__file__).parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/prompts/dod-gate.md"
)


def test_the_prompt_names_both_marks_the_goal_renders() -> None:
    text = " ".join(_PROMPT.read_text(encoding="utf-8").split())

    assert "--- BEGIN ITEM DEFINITION OF DONE" in text
    assert "--- END ITEM DEFINITION OF DONE ---" in text


def test_the_prompt_refuses_to_grade_a_line_quoted_in_a_ledger_comment() -> None:
    text = " ".join(_PROMPT.read_text(encoding="utf-8").split())

    assert "Never refuse an item on a line you found only in a comment" in text
    assert "`livespec-needs-human-cause`" in text

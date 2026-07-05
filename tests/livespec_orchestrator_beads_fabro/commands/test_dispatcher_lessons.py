"""Tests for the ratified-lessons reader (`_dispatcher_lessons`).

Covers the read side of the dispatch-brief lessons-injection contract in
SPECIFICATION/contracts.md (Scenarios 39-40): a committed ratified lesson
is extracted from `loop-reflection-gate/lessons.md`, while an absent,
placeholder-only, malformed (no `## Lessons` heading), or unreadable file
all fail open to the empty string. Only committed working-tree content is
read, so unmerged reflector proposals never surface here.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
)

_PLACEHOLDER = (
    "_No ratified lessons yet. The reflector will propose additions via PR; a\n"
    "human merges to ratify._"
)
_RATIFIED_LESSON = "Prefer explicit kw-only args in new dispatcher helpers."


def _write_lessons(*, root: Path, body: str) -> None:
    target = root / "loop-reflection-gate" / "lessons.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


def test_reads_ratified_lesson_text(tmp_path: Path) -> None:
    # The proposer APPENDS a ratified lesson after the placeholder, so a
    # ratified file carries both; the reader must surface the lesson and
    # drop the placeholder paragraph.
    _write_lessons(
        root=tmp_path,
        body=(
            "# Loop-reflection lessons (human-ratified)\n\n"
            "## Lessons\n\n"
            f"{_PLACEHOLDER}\n\n"
            f"{_RATIFIED_LESSON}\n"
        ),
    )
    result = read_ratified_lessons(lessons_root=tmp_path)
    assert _RATIFIED_LESSON in result
    assert "No ratified lessons yet" not in result


def test_absent_file_is_empty(tmp_path: Path) -> None:
    assert read_ratified_lessons(lessons_root=tmp_path) == ""


def test_placeholder_only_is_empty(tmp_path: Path) -> None:
    _write_lessons(
        root=tmp_path,
        body=(
            "# Loop-reflection lessons (human-ratified)\n\n" "## Lessons\n\n" f"{_PLACEHOLDER}\n"
        ),
    )
    assert read_ratified_lessons(lessons_root=tmp_path) == ""


def test_missing_heading_is_empty(tmp_path: Path) -> None:
    _write_lessons(
        root=tmp_path,
        body="# Loop-reflection lessons (human-ratified)\n\nIntro prose only.\n",
    )
    assert read_ratified_lessons(lessons_root=tmp_path) == ""


def test_unreadable_file_is_empty(tmp_path: Path) -> None:
    # A lessons.md that is a directory makes read_text raise OSError; the
    # reader must fail open rather than propagate.
    (tmp_path / "loop-reflection-gate" / "lessons.md").mkdir(parents=True)
    assert read_ratified_lessons(lessons_root=tmp_path) == ""

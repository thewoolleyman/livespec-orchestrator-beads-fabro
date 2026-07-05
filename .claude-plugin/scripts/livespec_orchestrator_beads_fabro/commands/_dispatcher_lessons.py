"""Ratified-lessons reader — the consumer half of the reflection gate's
human-ratified lessons loop (epic livespec-impl-beads-29f decision 7; the
PROPOSER half is `GitPrLessonsProposer` in `_dispatcher_reflector_oob`).

Per the dispatch-brief lessons-injection contract in
SPECIFICATION/contracts.md (and SPECIFICATION/scenarios.md Scenarios
39-40): dispatch-brief composition sources lessons EXCLUSIVELY from the
committed `loop-reflection-gate/lessons.md`, injects the ratified lesson
text into the brief, and leaves the brief unchanged when the file is
absent, carries only its placeholder, or cannot be read. This module is
the read side of that contract; the wiring into `render_goal` is the
sibling slice.

Fail-open: an absent, unreadable, malformed (no `## Lessons` heading), or
placeholder-only file all yield the empty string; `read_ratified_lessons`
NEVER raises, matching the reflection gate's stability posture (reflection
never alters a dispatch verdict). Only committed working-tree content is
read, so an unmerged reflector proposal never influences a brief.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = ["LESSONS_RELATIVE_PATH", "read_ratified_lessons"]

LESSONS_RELATIVE_PATH = Path("loop-reflection-gate/lessons.md")
_LESSONS_HEADING = "## Lessons"
_PLACEHOLDER_MARKER = "No ratified lessons yet"


def read_ratified_lessons(*, lessons_root: Path) -> str:
    """Return ratified lesson text from the committed lessons.md, or '' (fail-open).

    Reads `<lessons_root>/loop-reflection-gate/lessons.md`, takes the body
    under the `## Lessons` heading (up to the next H2), drops the placeholder
    paragraph the proposer leaves in place, and returns the remaining ratified
    text stripped. Returns '' when the file is absent, unreadable, missing the
    `## Lessons` heading, or carries only the placeholder — never raising.
    """
    try:
        text = (lessons_root / LESSONS_RELATIVE_PATH).read_text(encoding="utf-8")
    except OSError:
        return ""
    if _LESSONS_HEADING not in text:
        return ""
    section = text.split(_LESSONS_HEADING, 1)[1].split("\n## ", 1)[0]
    kept = [
        paragraph.strip()
        for paragraph in section.split("\n\n")
        if paragraph.strip() and _PLACEHOLDER_MARKER not in paragraph
    ]
    return "\n\n".join(kept)

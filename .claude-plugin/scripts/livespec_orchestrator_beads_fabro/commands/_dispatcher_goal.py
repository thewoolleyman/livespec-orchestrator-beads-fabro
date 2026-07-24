"""Per-item goal-brief assembly for the Dispatcher.

Assembles the natural-language brief delivered to the Fabro phase graph
from a work-item's fields, its ledger comments, and any ratified
lessons, then routes the whole assembled brief through
`escape_minijinja_literal` (hosted in `_dispatcher_overlay`) so Fabro's
MiniJinja goal templating renders the untrusted prose verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard import (
    FACTORY_WORKFLOW_BOUNDARY_TEXT,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = [
    "render_goal",
]


def render_goal(
    *,
    item: WorkItem,
    repo: Path,
    branch: str,
    comments: tuple[WorkItemComment, ...] = (),
    lessons: str = "",
) -> str:
    """Render the per-item brief delivered to the phase graph.

    Item fields, ledger comments, and ratified lessons are assembled, then
    MiniJinja open delimiters are escaped so Fabro renders the prose verbatim.
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    spec_line = (
        f"Spec id: {item.spec_commitment_hint}\n" if item.spec_commitment_hint is not None else ""
    )
    acceptance_line = (
        f"\nAcceptance criteria:\n{item.acceptance_criteria}\n"
        if item.acceptance_criteria is not None
        else ""
    )
    notes_line = f"\nNotes:\n{item.notes}\n" if item.notes is not None else ""
    base = (
        f"Work-item: {item.id}\n"
        # The agent runs inside the Fabro sandbox's OWN fresh clone (cwd),
        # NOT this path: `repo` is the Dispatcher's host-side checkout (e.g.
        # /workspace/dispatch-target) and does not exist in the sandbox. A
        # bare `Repo: <path>` line let the PR-stage agent cd to the missing
        # host path and report "no committed work" (livespec-vtxt). Keep the
        # path for provenance but frame it unmistakably as NOT a cd target.
        f"Repo (target repository; you are ALREADY inside its isolated Fabro "
        f"sandbox clone — run every git/gh command in your CURRENT WORKING "
        f"DIRECTORY and NEVER cd to this path: it is the dispatcher's "
        f"host-side checkout and does NOT exist inside your sandbox): {repo}\n"
        f"Publish branch (push HEAD to this exact ref at the PR stage): {branch}\n"
        f"Rank: {item.rank}  Type: {item.type}\n"
        f"{gap_line}"
        f"{spec_line}"
        f"Title: {item.title}\n"
        "\n"
        "Factory branch boundary:\n"
        f"{FACTORY_WORKFLOW_BOUNDARY_TEXT}\n"
        "\n"
        "Description:\n"
        f"{item.description}\n"
        f"{acceptance_line}"
        f"{notes_line}"
    )
    # Ratified lessons (the S1 read side) inject in a clearly delimited
    # section BEFORE escaping, so escape_minijinja_literal neutralizes the
    # human-merged lesson text like every other interpolated field. Empty
    # lessons leave the brief byte-identical (no heading or placeholder
    # bleed-through), matching the fail-open contract.
    body = base
    if lessons:
        body += (
            "\nRatified lessons (human-merged via loop-reflection-gate/"
            "lessons.md; treat as standing guidance for this dispatch):\n"
            f"{lessons}\n"
        )
    # Escape AFTER assembly so EVERY interpolated field (title, description,
    # lessons, comments, repo path) is neutralized in one place: the whole
    # rendered goal is what flows into fabro's MiniJinja-templated graph
    # `goal` attribute and prompts (work-item livespec-impl-beads-ajv).
    if not comments:
        return escape_minijinja_literal(text=body)
    lines = [
        "",
        "Ledger comments (operator riders appended after filing; treat them as part of the brief):",
    ]
    for index, comment in enumerate(comments, start=1):
        lines.append(f"[{index}] {_comment_entry(comment=comment)}")
    return escape_minijinja_literal(text=body + "\n".join(lines) + "\n")


def _comment_entry(*, comment: WorkItemComment) -> str:
    """Format one rider as `(author, created_at) text`, dropping absent parts."""
    provenance = ", ".join(
        part for part in (comment.author, comment.created_at) if part is not None
    )
    if provenance == "":
        return comment.text
    return f"({provenance}) {comment.text}"

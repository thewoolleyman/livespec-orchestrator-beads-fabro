"""Per-item goal-brief assembly for the Dispatcher.

Assembles the natural-language brief delivered to the Fabro phase graph
from a work-item's fields, its ledger comments, and any ratified
lessons, then routes the whole assembled brief through
`escape_minijinja_literal` (hosted in `_dispatcher_minijinja_escape`) so Fabro's
MiniJinja goal templating renders the untrusted prose verbatim.

A recovery-placed dispatch's own section — the interrupted prior attempt a
seeded sandbox starts on — is rendered by `_dispatcher_goal_recovery` and handed
in, for the cohesion reason that module's docstring gives: it is authored by the
Dispatcher from the invocation's resume attributes rather than read off the item,
so it shares neither input nor provenance with anything assembled here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal_recovery import (
    InterruptedAttempt,
    interrupted_attempt_section,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_minijinja_escape import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_guard import (
    FACTORY_WORKFLOW_BOUNDARY_TEXT,
)
from livespec_orchestrator_beads_fabro.commands._plan_anchor import is_spec_commitment
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = [
    "GoalBriefMiniJinjaFinding",
    "minijinja_findings_detail",
    "minijinja_openers_in_goal_sources",
    "minijinja_openers_in_text",
    "render_goal",
]

_MINIJINJA_OPEN_DELIMITER_RE = re.compile(r"\{\{|\{%|\{#")


@dataclass(frozen=True, kw_only=True)
class GoalBriefMiniJinjaFinding:
    """One MiniJinja opener found before goal-brief escaping."""

    source: str
    opener: str


def minijinja_openers_in_goal_sources(
    *,
    item: WorkItem,
    comments: tuple[WorkItemComment, ...],
    lessons: str,
) -> tuple[GoalBriefMiniJinjaFinding, ...]:
    """Find MiniJinja openers in the unescaped goal-brief source fields."""
    fields: list[tuple[str, str | None]] = [
        ("title", item.title),
        ("description", item.description),
        ("acceptance", item.acceptance_criteria),
        ("notes", item.notes),
        ("lessons", lessons),
    ]
    findings: list[GoalBriefMiniJinjaFinding] = []
    for source, text in fields:
        findings.extend(minijinja_openers_in_text(source=source, text=text))
    for index, comment in enumerate(comments, start=1):
        findings.extend(
            minijinja_openers_in_text(
                source=_comment_source(index=index, comment=comment), text=comment.text
            )
        )
    return tuple(findings)


def minijinja_openers_in_text(
    *,
    source: str,
    text: str | None,
) -> tuple[GoalBriefMiniJinjaFinding, ...]:
    """Find MiniJinja openers in ONE untrusted text bound for the goal brief.

    The whole-brief preflight above grades every source at once, which is the
    right shape at dispatch time — by then every source is already on the
    record. A writer that is about to APPEND a new one needs the same detector
    a single text at a time and BEFORE its write, because a ledger comment is
    append-only and cannot be repaired afterwards. Sharing one function is what
    keeps the two from drifting: an opener the dispatch preflight would refuse
    can never be admitted by a writer that feeds it.
    """
    if text is None or text == "":
        return ()
    return tuple(
        GoalBriefMiniJinjaFinding(source=source, opener=match.group(0))
        for match in _MINIJINJA_OPEN_DELIMITER_RE.finditer(text)
    )


def minijinja_findings_detail(
    *,
    findings: tuple[GoalBriefMiniJinjaFinding, ...],
) -> str:
    """Render a refusal detail naming every offending goal-brief source."""
    sources = ", ".join(f"{finding.source} ({finding.opener})" for finding in findings)
    return (
        "goal brief contains MiniJinja opening delimiter before escaping; "
        f"offending source(s): {sources}"
    )


def render_goal(
    *,
    item: WorkItem,
    repo: Path,
    branch: str,
    comments: tuple[WorkItemComment, ...] = (),
    lessons: str = "",
    interrupted: InterruptedAttempt | None = None,
) -> str:
    """Render the per-item brief delivered to the phase graph.

    Item fields, ledger comments, and ratified lessons are assembled, then
    MiniJinja open delimiters are escaped so Fabro renders the prose verbatim.

    `interrupted` is the recovery placement a seeded dispatch was given, absent
    for every other route. It defaults to absent because every entry point that
    is not a recovery launch has no placement to narrate — and that default is
    also why the call site's own keyword is bound by a test: an omission here
    renders the plain brief and says nothing about the section it dropped.
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    # PRESENCE IS THE WRONG QUESTION HERE, and this site is the one where
    # getting it wrong contaminates the BRIEF rather than a routing decision.
    # `spec_commitment_hint` is overloaded: it also carries the `plan:<slug>`
    # anchor marker, so a presence test told every plan-stamped item's
    # implementing agent it was working under a commitment to ratified spec
    # text. Ask the discriminating question instead (`_plan_anchor`).
    spec_line = (
        f"Spec id: {item.spec_commitment_hint}\n"
        if is_spec_commitment(spec_id=item.spec_commitment_hint)
        else ""
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
    # The recovery placement rides immediately after the item's own fields and
    # BEFORE the lessons and the riders, because it is a fact about the tree the
    # agent is already standing on: a brief that names it after the standing
    # guidance has the agent read the whole brief before learning that its
    # working tree is somebody else's unfinished work.
    body = base + interrupted_attempt_section(attempt=interrupted)
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


def _comment_source(*, index: int, comment: WorkItemComment) -> str:
    label = comment.comment_id or f"#{index}"
    created = "" if comment.created_at is None else f" created {comment.created_at}"
    return f"ledger comment {label}{created}"

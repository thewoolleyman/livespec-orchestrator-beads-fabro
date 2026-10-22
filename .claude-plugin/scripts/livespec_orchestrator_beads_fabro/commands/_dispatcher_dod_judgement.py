"""Pure Definition-of-Done judgement subject and verdict parsing.

The admission and dispatch walls share this one rendering so a verdict is reused
only when the exact criteria, referenced specification headings and ledger riders
are unchanged.

WHAT THE SUBJECT CARRIES, AND WHY THE RIDERS ARE PART OF IT. `contracts.md`'s
one-rubric-one-subject clause puts the item's effective criteria, the body of
each heading its reference line names, and its ledger comments in the subject.
The riders are not decoration: an operator appends one precisely to narrow or
correct what the section asserts, so a judge that never read them grades a brief
the item has moved on from — and the node, whose goal DOES carry every rider,
then refuses a section the host taking passed.

AND WHY THE DISPATCHER'S OWN JUDGEMENT RECORDS ARE NOT. The same clause excludes
them, and the reason is mechanical rather than aesthetic: recording a verdict
appends a comment, so a subject that carried receipts would move the digest the
verdict was just taken against. No later taking could ever reuse it, every pass
would pay a model call, and every pass would append one more receipt — a subject
that grows without bound and a reuse rule that can never fire. The predicate is
`_dispatcher_dod_judgement_markers.is_judgement_record`, shared with the goal
renderer, because a second spelling of the marker is two answers to one question.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    is_judgement_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CAUSE_UNPARSEABLE_VERDICT",
    "JUDGEMENT_ADMITTED",
    "JUDGEMENT_HELD",
    "JUDGEMENT_UNAVAILABLE",
    "DodJudgement",
    "first_remedy",
    "judgement_subject",
    "judgement_subject_digest",
    "parse_judgement_reply",
]

JUDGEMENT_ADMITTED = "admitted"
JUDGEMENT_HELD = "rests-at-needs-human"
JUDGEMENT_UNAVAILABLE = "did-not-run"
CAUSE_UNPARSEABLE_VERDICT = "unparseable-verdict"

_H2 = re.compile(r"^##\s+(.+?)\s*$")
_H2_MARKER = "## "
_VERDICT_PASSED = "passed"
_VERDICT_FAILED = "failed"
_REMEDY_SEPARATOR = "; "
_UNRESOLVED_HEADING_BODY = "(this heading does not resolve in the governed spec tree)"
_ABSENT_CRITERIA_BODY = "(this item carries no effective acceptance criteria)"
# The riders' own heading in the subject, and what stands where they would be
# when the item carries none. The explicit absence is what keeps an item with no
# riders distinguishable from one whose riders were dropped, which is the
# difference between a brief that is complete and one that was truncated.
_RIDERS_HEADING = "## Ledger comments (operator riders; part of the brief)"
_ABSENT_RIDERS_BODY = "(this item carries no operator rider)"


@dataclass(frozen=True, kw_only=True)
class DodJudgement:
    """One judgement result, including the actionable held findings."""

    outcome: str
    findings: tuple[str, ...] = ()
    cause: str | None = None

    @property
    def holds(self) -> bool:
        """Whether this verdict requires a needs-human rest."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def finding_text(self) -> str:
        """All held findings in their received order."""
        return "\n".join(self.findings)


def judgement_subject(*, item: WorkItem, cwd: Path, comments: Sequence[str] = ()) -> str:
    """Render the criteria, every referenced heading body and every rider.

    `comments` is the item's ledger comment bodies, oldest first, exactly as the
    gate reads them. It defaults to EMPTY rather than being required, because
    three callers legitimately hold no sidecar — the two pure digest readings a
    test takes, and any caller whose comments could not be read — and in each the
    honest subject is the one with no rider section to show. A caller that has
    them and omits them renders a smaller subject and a different digest, so the
    one call site that matters is bound by its own test.
    """
    criteria = effective_criteria(item=item)
    section = definition_of_done(description=item.description)
    blocks = [
        f"work-item: {item.id}",
        f"title: {item.title}",
        "",
        "## Effective acceptance criteria",
        criteria.text if criteria.text else _ABSENT_CRITERIA_BODY,
    ]
    for reference in section.references:
        blocks.extend(
            (
                "",
                f"## Referenced heading: {reference}",
                _heading_body(repo=cwd, reference=reference),
            )
        )
    blocks.extend(("", _RIDERS_HEADING, _riders_body(comments=comments)))
    return "\n".join(blocks)


def judgement_subject_digest(*, item: WorkItem, cwd: Path, comments: Sequence[str] = ()) -> str:
    """Return the stable byte digest used to determine verdict reuse."""
    return hashlib.sha256(
        judgement_subject(item=item, cwd=cwd, comments=comments).encode("utf-8")
    ).hexdigest()


def parse_judgement_reply(*, reply: str) -> DodJudgement:
    """Read the final non-empty line of a host judgement reply."""
    line = _last_non_empty_line(reply=reply)
    if line is None:
        return _unreadable()
    decoded = parse_json(text=line)
    if isinstance(decoded, JsonParseFailure) or not isinstance(decoded, dict):
        return _unreadable()
    record = cast("dict[str, object]", decoded)
    if record.get("outcome") == _VERDICT_PASSED:
        return DodJudgement(outcome=JUDGEMENT_ADMITTED)
    if record.get("outcome") == _VERDICT_FAILED:
        return _failed_verdict(reason=record.get("failure_reason"))
    return _unreadable()


def first_remedy(*, findings: tuple[str, ...]) -> str | None:
    """Return the first finding's remedy, or the finding where no split exists."""
    if not findings:
        return None
    head = findings[0]
    _, separator, remedy = head.rpartition(_REMEDY_SEPARATOR)
    return remedy.strip() if separator else head.strip()


def _riders_body(*, comments: Sequence[str]) -> str:
    """Every rider's text, oldest first, with the Dispatcher's receipts dropped.

    A comment's TEXT is rendered and nothing else — no author, no timestamp —
    because both move without the brief moving, and either in the subject would
    retire a recorded verdict on an edit that changed no requirement.
    """
    riders = [body for body in comments if not is_judgement_record(body=body)]
    return "\n\n".join(riders) if riders else _ABSENT_RIDERS_BODY


def _unreadable() -> DodJudgement:
    return DodJudgement(outcome=JUDGEMENT_UNAVAILABLE, cause=CAUSE_UNPARSEABLE_VERDICT)


def _failed_verdict(*, reason: object) -> DodJudgement:
    if not isinstance(reason, str) or not reason.strip():
        return _unreadable()
    return DodJudgement(
        outcome=JUDGEMENT_HELD,
        findings=tuple(line.strip() for line in reason.splitlines() if line.strip()),
    )


def _last_non_empty_line(*, reply: str) -> str | None:
    for raw in reversed(reply.splitlines()):
        stripped = raw.strip()
        if stripped:
            return stripped
    return None


def _heading_body(*, repo: Path, reference: str) -> str:
    """Return an H2 section body, retaining an explicit absence when unresolved."""
    title = reference.removeprefix(_H2_MARKER)
    spec_root = repo / "SPECIFICATION"
    if not spec_root.is_dir():
        return _UNRESOLVED_HEADING_BODY
    for path in sorted(spec_root.glob("*.md")):
        read = attempt(action=lambda p=path: p.read_text(encoding="utf-8"), exceptions=(OSError,))
        if isinstance(read, AttemptFailure):
            continue
        body = _section_of(text=read, title=title)
        if body is not None:
            return body
    return _UNRESOLVED_HEADING_BODY


def _section_of(*, text: str, title: str) -> str | None:
    """Extract an H2 section through, but not including, the following H2."""
    collected: list[str] | None = None
    for raw in text.splitlines():
        match = _H2.match(raw)
        if match is None:
            if collected is not None:
                collected.append(raw)
            continue
        if collected is not None:
            break
        if match.group(1) == title:
            collected = [raw]
    return "\n".join(collected) if collected is not None else None

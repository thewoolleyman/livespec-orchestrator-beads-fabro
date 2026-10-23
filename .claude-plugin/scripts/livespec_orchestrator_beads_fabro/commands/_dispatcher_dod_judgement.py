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

AND WHY THE ITEM'S OWN FIELDS COME FIRST, VERBATIM. The clause's GOAL is the
item's rendered goal — title, description, effective criteria, notes, lessons and
riders — and the rubric grades the DESCRIPTION: its first heading, its bullets,
and the `### Host-captured` / `### Human-attested` positions that declare each
assertion's proof mode. The effective-criteria projection flattens all three
away, so a subject that showed only the projection left check 1 nothing to read
and reported every host-captured assertion as factory_captured (bd-ib-kt4mgw).
The fields are rendered as the goal renders them, without the goal's
host-varying lines (the checkout path, the publish branch, a rider's author and
time), because a digest that moved with the host would retire every verdict the
moment another host took the judgement.

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import read_ratified_lessons
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_block,
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
    "rubric_digest",
    "spec_tree_identity",
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
# The description is the item's own text, so it can carry any heading; the end
# marker is what keeps the subject's next heading from reading as the item's.
_DESCRIPTION_END = "(end of the item's description)"
_LESSONS_LABEL = (
    "Ratified lessons (human-merged via loop-reflection-gate/lessons.md; "
    "treat as standing guidance for this dispatch):"
)
# The riders' own heading in the subject, and what stands where they would be
# when the item carries none. The explicit absence is what keeps an item with no
# riders distinguishable from one whose riders were dropped, which is the
# difference between a brief that is complete and one that was truncated.
_RIDERS_HEADING = "## Ledger comments (operator riders; part of the brief)"
_ABSENT_RIDERS_BODY = "(this item carries no operator rider)"
# The governed spec tree, named where `_heading_body` names it, and the two
# halves of the identity the reuse digest folds in.
_SPEC_DIRNAME = "SPECIFICATION"
_SPEC_IDENTITY_LABEL = "ratified-spec-identity: "
_UNREADABLE_SPEC_IDENTITY = "unreadable"


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


def judgement_subject(
    *,
    item: WorkItem,
    cwd: Path,
    comments: Sequence[str] = (),
    governing: GoverningHeadingVerdict | None = None,
) -> str:
    """Render the item's goal fields, criteria, referenced heading bodies and riders.

    `comments` is the item's ledger comment bodies, oldest first, exactly as the
    gate reads them. It defaults to EMPTY rather than being required, because
    three callers legitimately hold no sidecar — the two pure digest readings a
    test takes, and any caller whose comments could not be read — and in each the
    honest subject is the one with no rider section to show. A caller that has
    them and omits them renders a smaller subject and a different digest, so the
    one call site that matters is bound by its own test.

    `governing` is the spec-stated judgement's own verdict about which clauses
    govern these assertions, which `contracts.md` makes the component this
    judgement consults rather than decides for itself. It defaults to ABSENT and
    the block then says so in words, because a subject that simply omitted it
    would leave the judge unable to tell a verdict of "nothing governs" from a
    judgement nobody took — and those have opposite consequences, the first
    foreclosing the finding and the second leaving the node its own search.
    """
    criteria = effective_criteria(item=item)
    section = definition_of_done(description=item.description)
    blocks = [
        f"work-item: {item.id}",
        f"title: {item.title}",
        "",
        "Description:",
        item.description,
        _DESCRIPTION_END,
        *_goal_fields(item=item, lessons=read_ratified_lessons(lessons_root=cwd)),
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
    blocks.extend(("", governing_heading_block(verdict=governing)))
    return "\n".join(blocks)


def _goal_fields(*, item: WorkItem, lessons: str) -> list[str]:
    """The goal's optional item fields, each present only when the goal shows it."""
    fields: list[str] = []
    if item.acceptance_criteria is not None:
        fields.extend(("", "Acceptance criteria:", item.acceptance_criteria))
    if item.notes is not None:
        fields.extend(("", "Notes:", item.notes))
    if lessons:
        fields.extend(("", _LESSONS_LABEL, lessons))
    return fields


def judgement_subject_digest(*, item: WorkItem, cwd: Path, comments: Sequence[str] = ()) -> str:
    """Return the stable byte digest used to determine verdict reuse.

    Taken over the subject AS IT STANDS BEFORE THE JUDGEMENT IS TAKEN — with no
    governing-heading verdict in it — together with the identity of the ratified
    tree that verdict would be taken against. The asymmetry is the point: the
    block is the OUTPUT of a judgement this digest decides whether to spend,
    so folding it in would make the digest depend on the answer and no recorded
    verdict could ever be reused.

    THE SPEC IDENTITY IS WHAT A RATIFIED CHANGE MOVES. The subject already
    carries the BODY of each heading the reference line names, so an edit to a
    cited clause retires a verdict on its own; what it cannot see is a clause
    the item does not cite, and since `bd-ib-m76p2n` the governing-heading
    verdict is a reading of the WHOLE tree. A scenario added before dispatch can
    therefore become the governing one for an item that cites it nowhere, which
    is exactly the verdict a reuse keyed on the item's own text would carry
    forward unchanged.
    """
    subject = judgement_subject(item=item, cwd=cwd, comments=comments)
    return hashlib.sha256(
        f"{subject}\n{_SPEC_IDENTITY_LABEL}{spec_tree_identity(cwd=cwd)}".encode()
    ).hexdigest()


def spec_tree_identity(*, cwd: Path) -> str:
    """The digest of the governed spec tree, or a word naming an unreadable one.

    A SELF-DESCRIBING word rather than the digest of nothing, for the reason
    `UNREADABLE_RUBRIC_DIGEST` is one: an empty or zero-length digest reads as a
    tree that exists and is empty, which would make every unreadable read agree
    with every other one and reuse a verdict across a change nobody could see.
    The files are read through the same glob `_heading_body` resolves a
    reference against, so the identity watches the tree the subject quotes from.
    """
    spec_root = cwd / _SPEC_DIRNAME
    if not spec_root.is_dir():
        return _UNREADABLE_SPEC_IDENTITY
    digest = hashlib.sha256()
    for path in sorted(spec_root.glob("*.md")):
        read = attempt(action=lambda p=path: p.read_bytes(), exceptions=(OSError,))
        if isinstance(read, AttemptFailure):
            return _UNREADABLE_SPEC_IDENTITY
        digest.update(path.name.encode("utf-8"))
        digest.update(read)
    return digest.hexdigest()


def rubric_digest(*, rubric: str) -> str:
    """The digest of the ONE rubric every taking grades by: the gate prompt's bytes.

    It is here rather than beside the file read because the gate needs it BEFORE
    it decides whether to run anything, and because a digest computed in two
    places is two answers to "is this the rubric that verdict was taken under" —
    one of which would let a verdict be reused across the very rubric change
    that invalidates it.
    """
    return hashlib.sha256(rubric.encode("utf-8")).hexdigest()


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
    spec_root = repo / _SPEC_DIRNAME
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

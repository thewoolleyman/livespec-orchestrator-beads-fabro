"""The Definition-of-Done JUDGEMENT as a value, taken before a sandbox is spent.

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
("Judged before admission" and "Judged again before dispatch") moves the
SEMANTIC half of the gate — the half `_dispatcher_definition_of_done_findings`
deliberately leaves to the `dod_gate` node — onto the host, so an authoring
defect becomes a ledger finding instead of a spent dispatch. This module is the
PURE core of that move: what the judgement is handed, the digest that decides
whether an earlier verdict still covers it, and how its reply is read.

WHAT THE SUBJECT IS, AND WHY IT IS ONE STRING. The clause names two inputs —
"its effective criteria and referenced specification headings" — and states the
reuse rule in BYTES: a recorded verdict is reused "while the item's effective
criteria and referenced headings are byte-unchanged since that verdict was
taken". A digest over two separately-serialized inputs would be two digests a
caller could compare in either order, and comparing the wrong one reuses a
verdict taken against different text. One rendered subject makes the comparison
total: the bytes the judgement READ are the bytes the digest covers.

WHY A HEADING THAT DOES NOT RESOLVE IS RENDERED AS A STATED ABSENCE RATHER THAN
SKIPPED. A reference naming a heading the spec tree does not carry is what the
mechanical wall already refuses, so the judgement rarely sees one — but when it
does, dropping the line would make the subject of an item referencing a missing
heading byte-identical to the subject of the same item referencing nothing at
all. Those are different items to judge and must digest differently.

WHY AN UNPARSEABLE REPLY IS `did-not-run` AND NEVER `admitted`. The clause
enumerates "no eligible model, a timeout, or an unparseable verdict" together as
the conditions under which the judgement CANNOT RUN, and requires all three to
route the item as it would be routed without the judgement while recording why.
Reading an unparseable reply as a pass reaches the same routing by asserting
something false — that the judgement ran and admitted the item — and the record
is what a later reader uses to tell a judged item from an unjudged one.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
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

if TYPE_CHECKING:
    from pathlib import Path

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

# The three outcomes, each named for what it IS rather than numbered, as the
# enumeration rule requires of every mode-adjacent value in this tree.
JUDGEMENT_ADMITTED = "admitted"
JUDGEMENT_HELD = "rests-at-needs-human"
JUDGEMENT_UNAVAILABLE = "did-not-run"

# One of the three conditions the clause names as "cannot be run". The other two
# are properties of the INVOCATION rather than of the reply, so they are named
# by `_dispatcher_dod_judgement_run` beside the call that can observe them.
CAUSE_UNPARSEABLE_VERDICT = "unparseable-verdict"

_SPEC_DIRNAME = "SPECIFICATION"
_SPEC_FILE_GLOB = "*.md"
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_H2_MARKER = "## "
# What the host-side ending contract asks the judge to put on its last line. The
# node's own ending emits only the FAILING object, because a passing run falls
# through the graph; a host call has no graph to fall through, so the passing
# object is what distinguishes a pass from a reply nobody could read.
_VERDICT_PASSED = "passed"
_VERDICT_FAILED = "failed"
# How a finding line separates its account of the fault from its remedy. The
# gate's prompt requires every finding to carry one, and the mechanical wall's
# own findings are written in exactly this shape.
_REMEDY_SEPARATOR = "; "
_UNRESOLVED_HEADING_BODY = "(this heading does not resolve in the governed spec tree)"
_ABSENT_CRITERIA_BODY = "(this item carries no effective acceptance criteria)"


@dataclass(frozen=True, kw_only=True)
class DodJudgement:
    """One taking of the judgement: what it decided, and what it said.

    `findings` is populated only for `JUDGEMENT_HELD` and carries ONE LINE PER
    FINDING, in the order the judge reported them, because the clause requires
    "the verdict, with each remedy" to reach the ledger and the operator edits
    the section once.

    `cause` is populated only for `JUDGEMENT_UNAVAILABLE` and is deliberately
    COARSE — one stable string per condition rather than a message carrying an
    exit code or a path. The clause caps the did-not-run record at "once per
    distinct cause", so a cause that varied per invocation would make every
    attempt distinct and turn the cap into no cap at all.
    """

    outcome: str
    findings: tuple[str, ...] = ()
    cause: str | None = None

    @property
    def holds(self) -> bool:
        """Whether this verdict rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def finding_text(self) -> str:
        """Every finding as one block, which is what a refusal names."""
        return "\n".join(self.findings)


def judgement_subject(*, item: WorkItem, cwd: Path) -> str:
    """Exactly what the judgement is handed for one item, as rendered text.

    The two inputs the clause names, in a fixed order under fixed labels, so the
    same item renders the same bytes on every host: the item's identity, its
    effective criteria, and the body of each heading its reference line names.
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
    return "\n".join(blocks)


def judgement_subject_digest(*, item: WorkItem, cwd: Path) -> str:
    """The digest a recorded verdict is compared against to decide reuse."""
    return hashlib.sha256(judgement_subject(item=item, cwd=cwd).encode("utf-8")).hexdigest()


def parse_judgement_reply(*, reply: str) -> DodJudgement:
    """Read one judge reply's LAST line as the verdict it was asked to end on.

    The last NON-EMPTY line, because a reply ending in a trailing newline is the
    ordinary shape and reading the empty string after it would report every
    well-formed verdict as unparseable.
    """
    line = _last_non_empty_line(reply=reply)
    if line is None:
        return _unreadable()
    decoded = parse_json(text=line)
    if isinstance(decoded, JsonParseFailure) or not isinstance(decoded, dict):
        return _unreadable()
    record = cast("dict[str, object]", decoded)
    outcome = record.get("outcome")
    if outcome == _VERDICT_PASSED:
        return DodJudgement(outcome=JUDGEMENT_ADMITTED)
    if outcome == _VERDICT_FAILED:
        return _failed_verdict(reason=record.get("failure_reason"))
    return _unreadable()


def first_remedy(*, findings: tuple[str, ...]) -> str | None:
    """The remedy of the FIRST finding, which is what a hygiene fact names.

    The gate's prompt requires every finding line to end in the edit that would
    clear it, after the account of the fault. Where a line carries no separator
    the whole line IS the most specific thing available, so it is returned
    rather than dropped: a hygiene fact naming nothing is a row an operator
    cannot act on, which is the one thing the listing exists to prevent.
    """
    if not findings:
        return None
    head = findings[0]
    _, separator, remedy = head.rpartition(_REMEDY_SEPARATOR)
    return remedy.strip() if separator else head.strip()


def _unreadable() -> DodJudgement:
    return DodJudgement(outcome=JUDGEMENT_UNAVAILABLE, cause=CAUSE_UNPARSEABLE_VERDICT)


def _failed_verdict(*, reason: object) -> DodJudgement:
    """A `failed` object's findings, or `did-not-run` when it names none.

    A verdict saying the item failed while naming nothing an operator could
    repair is not a verdict: holding the item on it would rest it with a
    question nobody can answer, which is exactly what the node's own ending
    contract forbids. It is reported as unreadable instead, so the item routes
    as it would without the judgement and the record says the reply could not
    be read.
    """
    if not isinstance(reason, str) or reason.strip() == "":
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
    """One referenced heading's own section text, verbatim, or a stated absence.

    The body runs from the heading line to the next H2, which is the unit the
    judge reads the assertion against. Both reference forms resolve, `## <title>`
    and the bare `<title>`, exactly as the mechanical wall's H2 set admits both.
    """
    title = reference[len(_H2_MARKER) :] if reference.startswith(_H2_MARKER) else reference
    spec_root = repo / _SPEC_DIRNAME
    if not spec_root.is_dir():
        return _UNRESOLVED_HEADING_BODY
    for path in sorted(spec_root.glob(_SPEC_FILE_GLOB)):
        read = attempt(action=lambda p=path: p.read_text(encoding="utf-8"), exceptions=(OSError,))
        if isinstance(read, AttemptFailure):
            continue
        body = _section_of(text=read, title=title)
        if body is not None:
            return body
    return _UNRESOLVED_HEADING_BODY


def _section_of(*, text: str, title: str) -> str | None:
    """One H2's own lines, from its heading to the next H2, or None when absent."""
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

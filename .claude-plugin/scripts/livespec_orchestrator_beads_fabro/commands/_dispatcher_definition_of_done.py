"""The Definition of Done section of a work-item description, parsed ONCE.

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md` (v114)
makes this section the FIRST criteria source and says outright that "no surface
may parse the section by another path". This module is that path. It is
deliberately PURE — a function of the description text alone — because three
surfaces with three different amounts of context consume it: the criteria
primitive (which holds only the item), the host-side wall (which also holds the
repository), and the capture and groom displays.

WHY THE FIRST HEADING DECIDES. The clause requires the section as the
description's FIRST heading, so a description whose first heading is something
else does NOT carry the section even when a later heading is titled
`Definition of Done`. That is not pedantry: the whole point of a fixed position
is that a reader and a parser find the same section, and "the first heading I
happen to match" would let a Context or Notes section quietly host a second
definition that nothing grades.

WHY HEADINGS AND THE REFERENCE LINE ARE NOT ASSERTIONS. The clause says the
body consists of bullets plus exactly one `References:` line, and that the
reference line "MUST NOT be counted as a gradeable assertion by any parse".
Both exclusions happen HERE rather than in `criteria_lines`, because
`criteria_lines` is the general segmenter shared with the two legacy sources and
neither of them has a reference line to exclude. Leaving the exclusion to the
segmenter is also how the sub-heading would have leaked: `### Human-attested`
is neither short-and-shouting nor colon-terminated, so the segmenter's
header heuristic reads it as prose and would grade it as an assertion.

WHY THE TWO OPT-OUT SUB-HEADINGS SHARE ONE TABLE. `### Host-captured` (v115) and
`### Human-attested` differ in WHICH mode they declare and in nothing else this
parse does: each names exactly one mode and each returns the mode to the
default at the next heading. Adding the first as a second branch beside the
second would have been the smaller diff, and its cost is the failure nobody
sees — a later clause that tightens one sub-heading's handling and silently
leaves the other where it was, which reads as working code because both halves
still parse. One table is what makes the two structurally incapable of drifting
apart.

WHAT `subject` DECIDES, AND WHAT IT DOES NOT. The clause gives this primitive one
parameter, `subject`, whose value is `work-item` for every work item and `plan`
for a plan epic. The GRAMMAR is identical either way — same heading, same
bullets, same sub-headings, same reference-line shape. Two things differ, and
each is a per-subject TABLE rather than a branch, for the drift reason above:
the mode a bullet carries outside any sub-heading (`_DEFAULT_MODES` — a plan
bullet is `host_captured`, and `factory_captured` is not reachable for a plan
at all, since no factory run executes against an epic), and which opt-out
sub-headings owe a `Reason:` line (`_REASON_OWING_SUB_HEADINGS` — for a plan
only `Human-attested` does, because `Host-captured` declares the plan default
and so is permitted and redundant). Everything else about a plan section — that
zero or one reference line is valid, that a present one is validated exactly as
a work item's — needs no code here, because this parse never required a
reference line in the first place; it REPORTS what it found and the findings
surfaces decide what is owed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    criteria_lines,
)

__all__: list[str] = [
    "DEFINITION_OF_DONE_TITLE",
    "HOST_CAPTURED_SUB_HEADING_TITLE",
    "HUMAN_ATTESTED_SUB_HEADING_TITLE",
    "PROOF_MODE_FACTORY_CAPTURED",
    "PROOF_MODE_HOST_CAPTURED",
    "PROOF_MODE_HUMAN_ATTESTED",
    "REASON_PREFIX",
    "REFERENCES_PREFIX",
    "SUBJECT_PLAN",
    "SUBJECT_WORK_ITEM",
    "DefinitionOfDone",
    "DefinitionOfDoneAssertion",
    "declared_proof_mode",
    "definition_of_done",
]

DEFINITION_OF_DONE_TITLE = "definition of done"
REFERENCES_PREFIX = "References:"
REASON_PREFIX = "Reason:"
HOST_CAPTURED_SUB_HEADING_TITLE = "host-captured"
HUMAN_ATTESTED_SUB_HEADING_TITLE = "human-attested"
# The closed proof-mode enumeration. Every value is a SELF-DESCRIBING name on
# every surface that renders, journals or configures them, which the clause
# requires explicitly: a numbered or tiered label MUST NOT be used.
PROOF_MODE_FACTORY_CAPTURED = "factory_captured"
PROOF_MODE_HOST_CAPTURED = "host_captured"
PROOF_MODE_HUMAN_ATTESTED = "human_attested"

# The closed `subject` enumeration. Each value NAMES what it is, per the
# repository rule that an option set is never labelled as numbered tiers.
SUBJECT_WORK_ITEM = "work-item"
SUBJECT_PLAN = "plan"

# The sub-headings that OPT OUT of the default mode, keyed by case-folded title.
# This table is the WHOLE of the difference between the two: membership decides
# which mode the bullets under a sub-heading carry AND which sub-headings owe a
# `Reason:` line, so neither question can be answered for one of them and
# forgotten for the other.
_SUB_HEADING_MODES = {
    HOST_CAPTURED_SUB_HEADING_TITLE: PROOF_MODE_HOST_CAPTURED,
    HUMAN_ATTESTED_SUB_HEADING_TITLE: PROOF_MODE_HUMAN_ATTESTED,
}

# The mode a bullet carries when no sub-heading declares one, PER SUBJECT. This
# table is the whole of why a plan assertion can never be `factory_captured`:
# the value is simply not reachable for `plan`, rather than filtered out after
# the fact somewhere a later edit could miss.
_DEFAULT_MODES = {
    SUBJECT_WORK_ITEM: PROOF_MODE_FACTORY_CAPTURED,
    SUBJECT_PLAN: PROOF_MODE_HOST_CAPTURED,
}

# Which opt-out sub-headings owe a `Reason:` line, PER SUBJECT. For a work item
# both do. For a plan only `Human-attested` does: `Host-captured` declares the
# plan DEFAULT, so it is permitted and redundant, and a reason line justifying
# the default would be a sentence with no content to carry.
_REASON_OWING_SUB_HEADINGS = {
    SUBJECT_WORK_ITEM: frozenset(_SUB_HEADING_MODES),
    SUBJECT_PLAN: frozenset({HUMAN_ATTESTED_SUB_HEADING_TITLE}),
}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# Where ONE reference ends and the next begins. The clause writes the line as
# `References: <heading>[, <heading>...]`, but a ratified H2 heading carries
# commas OF ITS OWN — `## Scenario 133 — A mixed item is refused ai-only from
# every entry path, parks for its human-attested leg, and the accept valve
# refuses until the record exists` has two. Splitting on every `, ` therefore
# shreds one valid heading into three unresolvable fragments and reports three
# findings against a conforming item, which reads exactly like a real defect.
# Each reference is the verbatim text of a heading, so the separator is a comma
# followed by the next heading's own marker.
_REFERENCE_SEPARATOR = re.compile(r",\s+(?=#)")


@dataclass(frozen=True, kw_only=True)
class DefinitionOfDoneAssertion:
    """One gradeable assertion of a Definition of Done, with the mode it declared."""

    text: str
    proof_mode: str


@dataclass(frozen=True, kw_only=True)
class DefinitionOfDone:
    """One description's Definition of Done section, as the ratified parse reads it.

    `present` is False both when the description carries no heading at all and
    when its first heading is titled something else — the two are the same fact
    for every consumer, which is that this item has no Definition of Done.

    `criteria_text` is the section body with every heading line and the
    `References:` and `Reason:` lines removed, so it is exactly the text the
    shared segmenter should see. It is `None` for an absent section AND for a
    present one whose body carries no bullet, so a caller cannot accidentally
    read an empty section as gradeable.

    `assertions` carries the same segmentation in the section's own order, each
    one paired with the mode its POSITION declared. Document order is preserved
    rather than grouped by mode, because the proof record is published "per
    assertion in Definition of Done order" and the acceptance evidence leg
    indexes one against the other.

    `references` is the heading texts the reference line named, verbatim and in
    order. An empty tuple covers BOTH an absent reference line and one whose
    payload is blank, because the clause treats each the same way: the section
    carries no valid reference line.

    `malformed_proof_modes` carries the verbatim title of every opt-out
    sub-heading that OWES a non-empty `Reason:` line for this subject and
    reached none — both of them for a work item, and `Human-attested` alone for
    a plan. The assertions under such a sub-heading KEEP the mode it
    declared: the declaration is malformed, not absent, and silently downgrading
    it to the default would let the item auto-close with no host or human leg at
    all — the one outcome the sub-heading exists to prevent. The TITLE rather
    than the mode is carried because the finding quotes the sub-heading the
    author wrote; the mode is recovered from it by `declared_proof_mode` — which
    takes the same `subject`, so a plan's title cannot be resolved under the
    work-item defaults.
    """

    present: bool
    criteria_text: str | None
    assertions: tuple[DefinitionOfDoneAssertion, ...]
    references: tuple[str, ...]
    malformed_proof_modes: tuple[str, ...]

    @property
    def host_captured_assertions(self) -> tuple[str, ...]:
        """The assertion texts an agent session must capture on a host, in section order."""
        return self._with_mode(mode=PROOF_MODE_HOST_CAPTURED)

    @property
    def human_attested_assertions(self) -> tuple[str, ...]:
        """The assertion texts a human must attest, in section order."""
        return self._with_mode(mode=PROOF_MODE_HUMAN_ATTESTED)

    def _with_mode(self, *, mode: str) -> tuple[str, ...]:
        return tuple(one.text for one in self.assertions if one.proof_mode == mode)


def definition_of_done(*, description: str, subject: str = SUBJECT_WORK_ITEM) -> DefinitionOfDone:
    """Parse one description's Definition of Done section.

    `subject` is `work-item` for every work item and `plan` for a plan epic. The
    grammar is otherwise identical; what the subject decides is the mode a bullet
    carries outside any sub-heading, and which opt-out sub-headings owe a
    `Reason:` line. It defaults to `work-item` because that is every caller but
    the plan front-end, and because a wrong default there would silently drop a
    work item's factory leg rather than refuse.
    """
    lines = description.splitlines()
    opening = _opening_heading(lines=lines)
    if opening is None:
        return _absent()
    index, level, title = opening
    if title != DEFINITION_OF_DONE_TITLE:
        return _absent()
    body = _section_body(lines=lines, start=index + 1, level=level)
    assertions = _assertions(body=body, subject=subject)
    text = "\n".join(one.text for one in assertions)
    return DefinitionOfDone(
        present=True,
        criteria_text=text or None,
        assertions=assertions,
        references=_references(body=body),
        malformed_proof_modes=_malformed_proof_modes(body=body, subject=subject),
    )


def declared_proof_mode(*, sub_heading: str, subject: str = SUBJECT_WORK_ITEM) -> str:
    """The mode the bullets under one sub-heading declare.

    Only `Host-captured` and `Human-attested` opt out. Any other sub-heading is
    ordinary grouping and returns the mode to the SUBJECT'S DEFAULT, so a section
    cannot drift out of mechanical proof by introducing a heading that merely
    looks related.

    PUBLIC because the finding the host-side wall renders has to name the mode
    whose declaration is malformed, and it holds the verbatim sub-heading title
    rather than the mode. A second title-to-mode mapping over there is how the
    wall would come to report `human_attested` for a `Host-captured` sub-heading.
    """
    return _SUB_HEADING_MODES.get(sub_heading.strip().casefold(), _DEFAULT_MODES[subject])


def _absent() -> DefinitionOfDone:
    return DefinitionOfDone(
        present=False,
        criteria_text=None,
        assertions=(),
        references=(),
        malformed_proof_modes=(),
    )


def _assertions(*, body: list[str], subject: str) -> tuple[DefinitionOfDoneAssertion, ...]:
    """Segment the section body into assertions, each carrying its declared mode.

    The body is walked in order and split into RUNS of consecutive lines sharing
    one mode; each run is handed whole to the shared segmenter, so a bullet that
    carries two sentences yields two assertions exactly as it does from a legacy
    source. Segmenting run by run rather than line by line is what keeps an
    indented continuation attached to the bullet it wraps.
    """
    assertions: list[DefinitionOfDoneAssertion] = []
    mode = _DEFAULT_MODES[subject]
    run: list[str] = []
    for raw in body:
        heading = _HEADING.match(raw)
        if heading is not None:
            assertions.extend(_segment(run=run, mode=mode))
            run = []
            mode = declared_proof_mode(sub_heading=heading.group(2), subject=subject)
            continue
        if _is_section_prose(text=raw):
            continue
        run.append(raw)
    assertions.extend(_segment(run=run, mode=mode))
    return tuple(assertions)


def _segment(*, run: list[str], mode: str) -> list[DefinitionOfDoneAssertion]:
    text = "\n".join(run).strip()
    return [
        DefinitionOfDoneAssertion(text=one, proof_mode=mode)
        for one in criteria_lines(criteria_text=text or None)
    ]


def _is_section_prose(*, text: str) -> bool:
    """Whether a body line is required prose rather than a gradeable assertion."""
    return text.strip().startswith((REFERENCES_PREFIX, REASON_PREFIX))


def _malformed_proof_modes(*, body: list[str], subject: str) -> tuple[str, ...]:
    """The opt-out sub-headings that reached no non-empty `Reason:` line.

    "Before its first bullet" is read as "before the sub-heading ends", which is
    the same thing for a conforming section and the forgiving reading for one
    whose author put the reason after the bullets. The strict reading would
    refuse an item whose reason IS stated, and the finding exists to make the
    missing capability or host surface visible, not to police line order.

    WHICH sub-headings are in scope is the SUBJECT'S question, read from
    `_REASON_OWING_SUB_HEADINGS` — a plan's `Host-captured` sub-heading declares
    the plan default and owes nothing.
    """
    owing = _REASON_OWING_SUB_HEADINGS[subject]
    malformed: list[str] = []
    pending: str | None = None
    for raw in body:
        heading = _HEADING.match(raw)
        if heading is not None:
            title = heading.group(2).strip()
            if pending is not None:
                malformed.append(pending)
            pending = title if title.casefold() in owing else None
            continue
        if pending is not None and _states_a_reason(text=raw):
            pending = None
    if pending is not None:
        malformed.append(pending)
    return tuple(malformed)


def _states_a_reason(*, text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith(REASON_PREFIX):
        return False
    return bool(stripped[len(REASON_PREFIX) :].strip())


def _references(*, body: list[str]) -> tuple[str, ...]:
    """The heading texts the section's reference line named, verbatim and in order.

    The FIRST reference line wins. The clause requires exactly one, and a second
    one is not a reason to discard the valid first: an item whose reference
    resolves is dispatchable, and refusing it for a duplicate line would be a
    stricter gate than the one that was ratified.
    """
    for line in body:
        stripped = line.strip()
        if not stripped.startswith(REFERENCES_PREFIX):
            continue
        payload = stripped[len(REFERENCES_PREFIX) :].strip()
        if not payload:
            return ()
        return tuple(part.strip() for part in _REFERENCE_SEPARATOR.split(payload))
    return ()


def _opening_heading(*, lines: list[str]) -> tuple[int, int, str] | None:
    """The description's FIRST heading as (index, level, case-folded title)."""
    for index, raw in enumerate(lines):
        heading = _HEADING.match(raw)
        if heading is not None:
            return index, len(heading.group(1)), heading.group(2).strip().casefold()
    return None


def _section_body(*, lines: list[str], start: int, level: int) -> list[str]:
    """The lines under a heading, up to the next heading at or above its level."""
    body: list[str] = []
    for raw in lines[start:]:
        heading = _HEADING.match(raw)
        if heading is not None and len(heading.group(1)) <= level:
            break
        body.append(raw)
    return body

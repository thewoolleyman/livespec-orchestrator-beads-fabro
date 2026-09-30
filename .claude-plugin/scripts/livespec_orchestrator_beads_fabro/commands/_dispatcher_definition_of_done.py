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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "DEFINITION_OF_DONE_TITLE",
    "REFERENCES_PREFIX",
    "DefinitionOfDone",
    "definition_of_done",
]

DEFINITION_OF_DONE_TITLE = "definition of done"
REFERENCES_PREFIX = "References:"

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
class DefinitionOfDone:
    """One description's Definition of Done section, as the ratified parse reads it.

    `present` is False both when the description carries no heading at all and
    when its first heading is titled something else — the two are the same fact
    for every consumer, which is that this item has no Definition of Done.

    `criteria_text` is the section body with every heading line and the
    `References:` line removed, so it is exactly the text the shared segmenter
    should see. It is `None` for an absent section AND for a present one whose
    body carries no bullet, so a caller cannot accidentally read an empty
    section as gradeable.

    `references` is the heading texts the reference line named, verbatim and in
    order. An empty tuple covers BOTH an absent reference line and one whose
    payload is blank, because the clause treats each the same way: the section
    carries no valid reference line.
    """

    present: bool
    criteria_text: str | None
    references: tuple[str, ...]


def definition_of_done(*, description: str) -> DefinitionOfDone:
    """Parse one description's Definition of Done section."""
    lines = description.splitlines()
    opening = _opening_heading(lines=lines)
    if opening is None:
        return DefinitionOfDone(present=False, criteria_text=None, references=())
    index, level, title = opening
    if title != DEFINITION_OF_DONE_TITLE:
        return DefinitionOfDone(present=False, criteria_text=None, references=())
    body = _section_body(lines=lines, start=index + 1, level=level)
    assertion_lines = [
        line
        for line in body
        if _HEADING.match(line) is None and not line.strip().startswith(REFERENCES_PREFIX)
    ]
    text = "\n".join(assertion_lines).strip()
    return DefinitionOfDone(
        present=True,
        criteria_text=text or None,
        references=_references(body=body),
    )


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

"""The `Proof of Done` POINTER section of a work-item description.

The pointer clause of `SPECIFICATION/contracts.md` (v114) says the Dispatcher
MUST write this section after merge, "after the Definition of Done section and
preserving it byte-for-byte, containing only: the pull request number, the
comment link of the latest `verified` record, its run id and timestamp, its
verdict, and — when the item has `human_attested` assertions — the comment link
of the human-attested record once it exists. The section MUST NOT copy proof
content." It also makes a pointer whose run id or comment id disagrees with the
latest record on the pull request a hygiene fact, which is why the section has to
be READ back as well as written: `pointer_in` is that reader.

WHY THE HEADING LEVEL IS INHERITED FROM THE DEFINITION OF DONE SECTION. The
reserved form is `## Definition of Done`, and for that form a `##` pointer
heading is right. But the clause permits "any heading level", and a `##` pointer
written under a `#` Definition of Done would be a SUBSECTION of it — its bullets
would then parse as Definition of Done assertions, and the item would acquire
five new ungradeable "assertions" (`Pull request: #11`, and so on) at the exact
moment it was accepted. Matching the level is what makes the section a sibling
rather than a child, for every level the clause allows.

WHY THE SPLICE IS IDEMPOTENT. A pointer is rewritten — on a re-dispatch, and
again when the human-attested record lands — so the writer replaces an existing
pointer section rather than appending a second one. Two pointer sections would
make "the pointer" ambiguous, and the staleness fact would then have two run ids
to compare and no rule for choosing between them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "PROOF_OF_DONE_POINTER_TITLE",
    "ProofPointer",
    "description_with_pointer",
    "description_with_updated_pointer",
    "pointer_in",
]

PROOF_OF_DONE_POINTER_TITLE = "Proof of Done"

_DEFINITION_OF_DONE_TITLE = "definition of done"
_POINTER_TITLE_FOLDED = PROOF_OF_DONE_POINTER_TITLE.casefold()
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*-\s+(?P<label>[^:]+):\s*(?P<value>.*)$")
_PULL_REQUEST_LABEL = "Pull request"
_RECORD_LABEL = "Verified record"
_RUN_LABEL = "Run"
_TIMESTAMP_LABEL = "Timestamp"
_VERDICT_LABEL = "Verdict"
_HOST_RECORD_LABEL = "Host-verified record"
_HUMAN_RECORD_LABEL = "Human-attested record"


@dataclass(frozen=True, kw_only=True)
class ProofPointer:
    """One item's pointer at the record that evidenced its merge.

    `human_attested_url` is `None` both for an item with no human-attested
    assertion and for one whose human record has not been posted yet. The two are
    the same fact for the section — there is no link to render — and they are
    told apart by the item's own Definition of Done, which is where the question
    belongs. `host_verified_url` is the v115 sibling and carries `None` on exactly
    the same terms, for the item's host leg.
    """

    pull_request: int
    record_url: str
    run_id: str
    timestamp: str
    verdict: str
    host_verified_url: str | None = None
    human_attested_url: str | None = None

    def render(self, *, heading_level: int = 2) -> str:
        """The section's own text, with no trailing newline.

        The two opt-out links are rendered in the order the clause lists them —
        host, then human — and each only when there is one. The clause says the
        section contains "only" the fields it names, so a bullet for a link that
        does not exist would be content the clause does not admit, and a reader
        would take an empty value for a record that had been published.
        """
        lines = [
            f"{'#' * heading_level} {PROOF_OF_DONE_POINTER_TITLE}",
            "",
            f"- {_PULL_REQUEST_LABEL}: #{self.pull_request}",
            f"- {_RECORD_LABEL}: {self.record_url}",
            f"- {_RUN_LABEL}: {self.run_id}",
            f"- {_TIMESTAMP_LABEL}: {self.timestamp}",
            f"- {_VERDICT_LABEL}: {self.verdict}",
        ]
        optional = (
            (_HOST_RECORD_LABEL, self.host_verified_url),
            (_HUMAN_RECORD_LABEL, self.human_attested_url),
        )
        lines.extend(f"- {label}: {url}" for label, url in optional if url is not None)
        return "\n".join(lines)

    def as_record(self) -> dict[str, object]:
        """The journal projection of what the pointer write recorded."""
        return {
            "pull_request": self.pull_request,
            "record_comment": self.record_url,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "verdict": self.verdict,
            "host_verified_record": self.host_verified_url,
            "human_attested_record": self.human_attested_url,
        }


def description_with_pointer(*, description: str, pointer: ProofPointer) -> str | None:
    """Splice the pointer in after the Definition of Done section.

    `None` when the description carries no Definition of Done section as its
    first heading: there is no anchor to write the pointer after, and appending it
    somewhere else would put the pointer where no reader of the clause expects it.
    The caller journals that rather than guessing a position.
    """
    lines = description.splitlines()
    anchor = _definition_of_done_heading(lines=lines)
    if anchor is None:
        return None
    index, level = anchor
    end = _section_end(lines=lines, start=index + 1, level=level)
    head = list(lines[:end])
    if head[-1].strip():
        head.append("")
    tail = _without_pointer_section(lines=lines[end:], level=level)
    body = [*head, *pointer.render(heading_level=level).splitlines(), "", *tail]
    return "\n".join(body).rstrip("\n") + "\n"


def description_with_updated_pointer(*, description: str, pointer: ProofPointer) -> str:
    """Rewrite an EXISTING pointer section in place, leaving everything else alone.

    Deliberately TOTAL where `description_with_pointer` is partial, because the
    two answer different questions. That one WRITES a pointer and therefore needs
    the Definition of Done section to anchor after; this one UPDATES a pointer
    that is already standing — the accept valve has just read it back — so the
    section's own position is the anchor and no second one is needed. A
    description carrying no pointer section is returned unchanged, which is the
    same answer as "there was nothing to update".
    """
    lines = description.splitlines()
    for index, raw in enumerate(lines):
        heading = _HEADING.match(raw)
        if heading is None or heading.group(2).strip().casefold() != _POINTER_TITLE_FOLDED:
            continue
        level = len(heading.group(1))
        end = _section_end(lines=lines, start=index + 1, level=level)
        body = [*lines[:index], *pointer.render(heading_level=level).splitlines(), *lines[end:]]
        return "\n".join(body).rstrip("\n") + "\n"
    return description


def pointer_in(*, description: str) -> ProofPointer | None:
    """Read back one description's pointer section, or `None` when it has none.

    A section whose pull-request bullet is missing or unparsable answers `None`
    too: the pull request is the one field every consumer of the pointer needs —
    the staleness fact reads the records off it and the attention surface links to
    it — so a section without it is not a usable pointer however much else it
    carries.
    """
    section = _pointer_section(description=description)
    if section is None:
        return None
    fields = _bullet_fields(lines=section)
    number = _pull_request_number(raw=fields.get(_PULL_REQUEST_LABEL))
    if number is None:
        return None
    return ProofPointer(
        pull_request=number,
        record_url=fields.get(_RECORD_LABEL, ""),
        run_id=fields.get(_RUN_LABEL, ""),
        timestamp=fields.get(_TIMESTAMP_LABEL, ""),
        verdict=fields.get(_VERDICT_LABEL, ""),
        host_verified_url=fields.get(_HOST_RECORD_LABEL),
        human_attested_url=fields.get(_HUMAN_RECORD_LABEL),
    )


def _definition_of_done_heading(*, lines: list[str]) -> tuple[int, int] | None:
    """The FIRST heading, when it is the Definition of Done, as (index, level).

    The first heading decides, exactly as the section parser decides: a
    description whose first heading is something else carries no Definition of
    Done section, and the pointer has nothing to anchor to.
    """
    for index, raw in enumerate(lines):
        heading = _HEADING.match(raw)
        if heading is None:
            continue
        if heading.group(2).strip().casefold() != _DEFINITION_OF_DONE_TITLE:
            return None
        return index, len(heading.group(1))
    return None


def _section_end(*, lines: list[str], start: int, level: int) -> int:
    """The index of the next heading at or above `level`, or the end of the text."""
    for offset, raw in enumerate(lines[start:], start=start):
        heading = _HEADING.match(raw)
        if heading is not None and len(heading.group(1)) <= level:
            return offset
    return len(lines)


def _without_pointer_section(*, lines: list[str], level: int) -> list[str]:
    """`lines` with a leading pointer section removed, so the splice replaces it."""
    if not lines:
        return []
    heading = _HEADING.match(lines[0])
    if heading is None or heading.group(2).strip().casefold() != _POINTER_TITLE_FOLDED:
        return lines
    return lines[_section_end(lines=lines, start=1, level=level) :]


def _pointer_section(*, description: str) -> list[str] | None:
    lines = description.splitlines()
    for index, raw in enumerate(lines):
        heading = _HEADING.match(raw)
        if heading is None or heading.group(2).strip().casefold() != _POINTER_TITLE_FOLDED:
            continue
        level = len(heading.group(1))
        return lines[index + 1 : _section_end(lines=lines, start=index + 1, level=level)]
    return None


def _bullet_fields(*, lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in lines:
        bullet = _BULLET.match(raw)
        if bullet is not None:
            fields[bullet.group("label").strip()] = bullet.group("value").strip()
    return fields


def _pull_request_number(*, raw: str | None) -> int | None:
    if raw is None:
        return None
    digits = raw.lstrip("#").strip()
    if not digits.isdigit():
        return None
    return int(digits)

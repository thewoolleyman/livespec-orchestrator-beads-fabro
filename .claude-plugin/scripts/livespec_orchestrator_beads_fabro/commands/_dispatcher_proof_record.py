"""The Proof of Done record comments of one pull request, parsed ONCE.

The Proof-of-Done-record clause of `SPECIFICATION/contracts.md` (v114, widened by
v115) fixes the record's first line — `Proof of Done — <captured|not_captured|
verified|not_reproduced|host_recorded|host_verified|host_not_reproduced|
human_attested> — <run <run-id> | session <session-identity> | human <identity>> —
<UTC timestamp>` — and
requires the body to carry, per assertion in Definition of Done order, the
assertion text, its proof mode, the reproduction steps and the proof. The
`proof_verify` prompt that PRODUCES the record writes the per-assertion
reproduction verdict as a `Reproduced:` line, and calls it out as "the
load-bearing line: the acceptance pass reads it per assertion". This module is
the reader of both halves.

WHY THE PER-ASSERTION ANSWER IS TRI-STATE. `reproduced` returns `None` as well
as `True`/`False`, and the third value is the one the evidence rule depends on:
an assertion the record does not mention, or mentions without a readable
`Reproduced:` line, is UNEVIDENCED — and the clause on unevidenceable assertions
says outright that such an assertion "is unevidenced, not failed". Collapsing
`None` into `False` would turn an absent observation into failing evidence,
route the item to rework, and consume an `acceptance_rework_cap` attempt the
clause forbids spending.

WHY MATCHING IS WHITESPACE-NORMALIZED AND SECTION-SCOPED. The record publishes
the assertion verbatim, but a record comment is prose: the publisher may hard-wrap
a long assertion across several physical lines, so a line-by-line substring search
finds nothing for exactly the assertions most likely to be long. The body is
therefore split into per-assertion SECTIONS at its headings and each section is
normalized whole before the search, which is wrap-independent for the same reason
the criteria segmenter is.

WHY THE SPLIT IS FENCE-AWARE. A heading-like line is only a heading when it is
PROSE, and the bulk of a record is not prose: the clause requires a fenced code
block per text capture, and the lines inside one routinely begin with a hash —
shell comments, Python comments, the printed headings of a Markdown file. Splitting
at those opened a new section mid-proof, so an assertion's section ended BEFORE its
own `Reproduced:` line and the reader answered `None` for an assertion the record
states was reproduced. Measured 2026-10-04 against the pre-repair reader, over two
verified records that were correctly attributed and correctly published: PR #2561
graded `[None, None, True, True]` and PR #2538 graded `[True, True, True, None]`,
so five of eight assertions read as unobserved and both items parked on
NEEDS_ATTENTION although every one of those sections carries `Reproduced: yes.`
The blast radius was any proof that prints a comment or a heading, which is most of
them.

WHY ONLY THE FENCE, AND NOT "SPLIT AT THE ASSERTION HEADINGS ONLY". The narrower
rule is the one that looks right and is measurably wrong. Recognising the record's
own `## Assertion N — ` form and treating nothing else as a boundary would still
split inside a fence, because a proof's SHELL COMMENTS take that form too: PR
#2561's captured record carries four fenced lines reading `# Assertion 2, Step 2:
…`, `# Assertion 3, Step 2: …` and the like. It would also stop splitting at a
trailing `## Verdict` or `## Summary`, which is the fail-OPEN direction — an
assertion whose own `Reproduced:` line is missing would absorb a later section's
and report evidence nobody published. Fence state answers the question the defect
actually asks, so it is the whole of the rule.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "PROOF_RECORD_TITLE",
    "PROOF_RECORD_VERDICTS",
    "VERDICT_CAPTURED",
    "VERDICT_HOST_NOT_REPRODUCED",
    "VERDICT_HOST_RECORDED",
    "VERDICT_HOST_VERIFIED",
    "VERDICT_HUMAN_ATTESTED",
    "VERDICT_NOT_CAPTURED",
    "VERDICT_NOT_REPRODUCED",
    "VERDICT_VERIFIED",
    "ProofRecord",
    "latest_proof_record",
    "proof_records",
]

PROOF_RECORD_TITLE = "Proof of Done"
VERDICT_CAPTURED = "captured"
# The verdict of a `proof_capture` execution that ended with
# `preferred_label=fix`: the capture could not be produced without a code change,
# so the record names the assertions it could not capture and the finding. It is
# in the enumeration because the finding has to SURVIVE the run — the `fix` node
# this routes to reads the latest record on the pull request when its preamble
# carries no finding, and a verdict outside the set is not a record at all, so
# the reader would drop the comment and report nothing.
VERDICT_NOT_CAPTURED = "not_captured"
VERDICT_VERIFIED = "verified"
VERDICT_NOT_REPRODUCED = "not_reproduced"
VERDICT_HUMAN_ATTESTED = "human_attested"
# The three HOST-LEG verdicts of v115: the capture an agent session publishes on
# an operator host, the independent replay that reproduces it, and the replay that
# does not. They deliberately share no word with the proof MODE `host_captured`,
# which the clause requires outright — a record verdict and a mode spelled the same
# way would make "host_captured" ambiguous on every surface that renders either.
VERDICT_HOST_RECORDED = "host_recorded"
VERDICT_HOST_VERIFIED = "host_verified"
VERDICT_HOST_NOT_REPRODUCED = "host_not_reproduced"
# The closed set the header's second field may carry. A comment whose first line
# is shaped like a record but names something else is NOT a record: the stages
# render the verdict verbatim, so an unknown value is prose that happens to open
# with the title, and reading it as a record would let arbitrary discussion
# masquerade as proof.
PROOF_RECORD_VERDICTS = (
    VERDICT_CAPTURED,
    VERDICT_NOT_CAPTURED,
    VERDICT_VERIFIED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    VERDICT_HOST_NOT_REPRODUCED,
)

# The ratified header separator is the em dash. The third field is the PUBLISHING
# IDENTITY, written as one of `run <run-id> | session <session-identity> | human
# <identity>` — the clause's own grammar, not a guess at a format. All three
# introducers are accepted and the one that matched is stripped, because the KIND
# of identity follows from the verdict rather than from a second field: a factory
# record carries a run, a host record a session, a human record a forge login.
#
# WHY A BARE IDENTITY IS STILL NOT A RECORD. The introducer is what separates a
# record header from prose that happens to open with the title and carry em
# dashes. Dropping the requirement would make any three-field sentence beginning
# `Proof of Done — verified —` into evidence.
_HEADER_SEPARATOR = "—"
_IDENTITY_PREFIXES = ("run ", "session ", "human ")
_HEADER_MINIMUM_FIELDS = 3
_TIMESTAMP_FIELD = 3
_HEADING = re.compile(r"^#{1,6}\s")
# A CommonMark fenced-code delimiter: three or more backticks or tildes, indented
# no more than three spaces. The run itself is captured because closing a fence
# depends on it; the info string an OPENING delimiter may carry is not, because
# nothing here reads it.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_WHITESPACE = re.compile(r"\s+")
_REPRODUCED_PREFIX = "reproduced:"
_REPRODUCED_YES = "yes"
_REPRODUCED_NO = "no"


@dataclass(frozen=True, kw_only=True)
class ProofRecord:
    """One published Proof of Done record comment.

    `url` is the comment link the pointer section and the acceptance journal
    both cite; it is an empty string when the forge payload carried none, which
    is a degraded read rather than a different kind of record.

    `run_id` is the header's third field with its introducer stripped, so it is a
    Fabro run id on a factory record, a SESSION IDENTITY on a host-leg record and a
    forge login on a human-attested one. The field keeps its name because the
    acceptance pass's attribution filter reads it for factory records and nothing
    else does; a host or human record is matched with `run_ids=None`, which is the
    unfiltered answer, so no caller compares a session identity against a run id.
    """

    verdict: str
    run_id: str
    timestamp: str
    url: str
    body: str

    def reproduced(self, *, assertion: str) -> bool | None:
        """Whether this record lists one assertion as reproduced.

        `None` means the record does not say — the assertion is absent from it,
        or its section carries no readable `Reproduced:` line. That is the
        unevidenced answer, deliberately distinct from `False`.
        """
        section = _assertion_section(body=self.body, assertion=assertion)
        if section is None:
            return None
        return _reproduced_in(section=section)


def proof_records(*, comments: Sequence[Mapping[str, object]]) -> tuple[ProofRecord, ...]:
    """Every Proof of Done record among one pull request's comments, in order.

    Order is the forge's own comment order, which is chronological, and it is
    what `latest_proof_record` reads "latest" off.
    """
    parsed = (_record(comment=comment) for comment in comments)
    return tuple(one for one in parsed if one is not None)


def latest_proof_record(
    *,
    records: Sequence[ProofRecord],
    verdict: str,
    run_ids: tuple[str, ...] | None = None,
) -> ProofRecord | None:
    """The newest record carrying one verdict, optionally for one dispatch.

    `run_ids` is the acceptance pass's attribution requirement: the clause asks
    for "the `proof_verify` record of the run whose pull request merged", so a
    verified record published by some OTHER dispatch is not this merge's
    evidence. It is a SET rather than one id because the clause requires EITHER
    identifier the Dispatcher can attribute to that dispatch to be accepted — the
    Fabro run id, or the dispatch id it declared to the sandbox
    (`_dispatcher_proof_attribution`).

    `None` is the UNFILTERED answer — the newest record of a verdict whoever
    published it — which the human-attested leg needs, because a human is not a
    run. An EMPTY tuple is the opposite, and the two must not be confused: a
    dispatch whose identifiers could not be resolved matches NO record rather
    than inheriting whichever one is newest.
    """
    matching = [
        one
        for one in records
        if one.verdict == verdict and (run_ids is None or one.run_id in run_ids)
    ]
    if not matching:
        return None
    return matching[-1]


def _record(*, comment: Mapping[str, object]) -> ProofRecord | None:
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    fields = _header_fields(body=body)
    if fields is None:
        return None
    identity = _identity(field=fields[2])
    if identity is None:
        return None
    url = comment.get("url")
    return ProofRecord(
        verdict=fields[1],
        run_id=identity,
        timestamp=fields[_TIMESTAMP_FIELD] if len(fields) > _TIMESTAMP_FIELD else "",
        url=url if isinstance(url, str) else "",
        body=body,
    )


def _header_fields(*, body: str) -> list[str] | None:
    """The record header's em-dash-separated fields, or `None` for a non-record."""
    lines = body.splitlines()
    if not lines:
        return None
    fields = [part.strip() for part in lines[0].split(_HEADER_SEPARATOR)]
    if len(fields) < _HEADER_MINIMUM_FIELDS:
        return None
    if fields[0] != PROOF_RECORD_TITLE or fields[1] not in PROOF_RECORD_VERDICTS:
        return None
    return fields


def _identity(*, field: str) -> str | None:
    """The identity the header's third field carries, or `None` for no introducer.

    `None` is what makes an introducer-less third field a NON-record rather than a
    record whose identity happens to be empty, which is the distinction the
    enumeration arm below relies on.
    """
    for prefix in _IDENTITY_PREFIXES:
        if field.startswith(prefix):
            return field[len(prefix) :].strip()
    return None


def _assertion_section(*, body: str, assertion: str) -> list[str] | None:
    needle = _normalized(text=assertion)
    if not needle:
        return None
    for section in _sections(body=body):
        if needle in _normalized(text=" ".join(section)):
            return section
    return None


def _sections(*, body: str) -> list[list[str]]:
    """The record body split at its PROSE headings, each heading opening a section.

    The accumulator starts as one OPEN section rather than as an empty list, so
    there is no end-of-body flush to get wrong: the lines before the first
    heading — the header line itself — are that open section, and a body with no
    lines at all is one empty section, which matches no assertion.

    A heading-like line INSIDE a fenced code block is proof output, not a heading,
    and never opens a section — the module docstring records what splitting at one
    cost. The delimiter line itself is never a heading either, so the fence arm and
    the heading arm are exclusive.
    """
    sections: list[list[str]] = [[]]
    fence: str | None = None
    for line in body.splitlines():
        delimiter = _FENCE.match(line)
        if delimiter is not None:
            fence = _fence_after(fence=fence, delimiter=delimiter.group(1))
        elif fence is None and _HEADING.match(line) is not None and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    return sections


def _fence_after(*, fence: str | None, delimiter: str) -> str | None:
    """The open fence after one delimiter line, or `None` outside a fence.

    The OPEN delimiter is carried rather than a boolean because CommonMark closes a
    fence only on its own character with at least as long a run, and a record
    legitimately nests one fence inside another: a proof that prints part of a
    Markdown file prints that file's own fences, and an excerpt can carry one half
    of a pair. A boolean inverts on that line and stays inverted, after which the
    splitter believes it is inside a fence for the rest of the body — two assertion
    sections merge and the first reports the second's verdict, which is the
    fail-OPEN answer the evidence rule forbids.
    """
    if fence is None:
        return delimiter
    if delimiter[0] == fence[0] and len(delimiter) >= len(fence):
        return None
    return fence


def _reproduced_in(*, section: list[str]) -> bool | None:
    for line in section:
        stripped = line.strip().casefold()
        if not stripped.startswith(_REPRODUCED_PREFIX):
            continue
        value = stripped[len(_REPRODUCED_PREFIX) :].strip()
        if value.startswith(_REPRODUCED_YES):
            return True
        if value.startswith(_REPRODUCED_NO):
            return False
    return None


def _normalized(*, text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()

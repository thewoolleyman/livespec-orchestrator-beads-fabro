"""The Proof of Done record comments of one pull request, parsed ONCE.

The Proof-of-Done-record clause of `SPECIFICATION/contracts.md` (v114, widened by
v115) fixes the record's first line — `Proof of Done — <captured|not_captured|
verified|not_reproduced|human_attested> — run <run-id or human identity> — <UTC
timestamp>` — and
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
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "PROOF_RECORD_TITLE",
    "PROOF_RECORD_VERDICTS",
    "VERDICT_CAPTURED",
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
)

# The ratified header separator is the em dash, with the run id introduced by the
# literal `run `. Both are the clause's own text, not a guess at a format.
_HEADER_SEPARATOR = "—"
_RUN_PREFIX = "run "
_HEADER_MINIMUM_FIELDS = 3
_TIMESTAMP_FIELD = 3
_HEADING = re.compile(r"^#{1,6}\s")
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
    url = comment.get("url")
    return ProofRecord(
        verdict=fields[1],
        run_id=fields[2][len(_RUN_PREFIX) :].strip(),
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
    if not fields[2].startswith(_RUN_PREFIX):
        return None
    return fields


def _assertion_section(*, body: str, assertion: str) -> list[str] | None:
    needle = _normalized(text=assertion)
    if not needle:
        return None
    for section in _sections(body=body):
        if needle in _normalized(text=" ".join(section)):
            return section
    return None


def _sections(*, body: str) -> list[list[str]]:
    """The record body split at its headings, each heading opening a section.

    The accumulator starts as one OPEN section rather than as an empty list, so
    there is no end-of-body flush to get wrong: the lines before the first
    heading — the header line itself — are that open section, and a body with no
    lines at all is one empty section, which matches no assertion.
    """
    sections: list[list[str]] = [[]]
    for line in body.splitlines():
        if _HEADING.match(line) is not None and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    return sections


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

"""The governing-heading verdict of a judgement record: its fields and its rendering.

Split from the record module, which is at its logical-line ceiling, along the line
that module already draws: this is the spec-stated judgement's verdict written
BESIDE the outcome, with the field names a reader of the record scans for.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_clause_record import clause_line
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

__all__: list[str] = [
    "GOVERNING_GENERALIZATION_FIELD",
    "GOVERNING_HEADING_FIELD",
    "GOVERNING_KIND_FIELD",
    "GOVERNING_NAMED_CLAUSE_FIELD",
    "GOVERNING_PROVENANCE_FIELD",
    "GOVERNING_SELECTED_CLAUSE_FIELD",
    "GOVERNING_SUBJECT_DIGEST_FIELD",
    "GoverningHeadingReceipt",
    "governing_record_lines",
]

# The spec-stated judgement's own verdict, recorded so the `dod_gate` node can
# be briefed with the verdict the host taking used rather than with a second
# one taken at the goal render. The heading key is REPEATED, one line per
# governing clause, exactly as `finding` is.
GOVERNING_KIND_FIELD = "governing-heading-kind"
GOVERNING_HEADING_FIELD = "governing-heading"
GOVERNING_SUBJECT_DIGEST_FIELD = "governing-heading-subject-digest"
GOVERNING_PROVENANCE_FIELD = "governing-heading-provenance"
GOVERNING_SELECTED_CLAUSE_FIELD = "governing-heading-selected-clause"
GOVERNING_NAMED_CLAUSE_FIELD = "governing-heading-named-clause"
GOVERNING_GENERALIZATION_FIELD = "governing-heading-generalization-target"
_FIELD_SEPARATOR = ": "


@dataclass(frozen=True, kw_only=True)
class GoverningHeadingReceipt:
    """The component verdict and exact non-spec input its record binds."""

    verdict: GoverningHeadingVerdict
    subject_digest: str


def governing_record_lines(*, governing: GoverningHeadingReceipt) -> list[str]:
    """The record lines one governing-heading receipt renders as."""
    verdict = governing.verdict
    provenance = "complete" if verdict.provenance_complete else "incomplete"
    lines = [
        f"{GOVERNING_KIND_FIELD}{_FIELD_SEPARATOR}{verdict.kind}",
        f"{GOVERNING_SUBJECT_DIGEST_FIELD}{_FIELD_SEPARATOR}{governing.subject_digest}",
        f"{GOVERNING_PROVENANCE_FIELD}{_FIELD_SEPARATOR}{provenance}",
    ]
    lines.extend(
        f"{GOVERNING_HEADING_FIELD}{_FIELD_SEPARATOR}{heading}" for heading in verdict.stated_by
    )
    if verdict.generalization_target is not None:
        target = verdict.generalization_target
        lines.append(f"{GOVERNING_GENERALIZATION_FIELD}{_FIELD_SEPARATOR}{target}")
    lines.extend(
        clause_line(key=GOVERNING_SELECTED_CLAUSE_FIELD, clause=clause)
        for clause in verdict.selected_clauses
    )
    lines.extend(
        clause_line(key=GOVERNING_NAMED_CLAUSE_FIELD, clause=clause)
        for clause in verdict.named_clauses
    )
    return lines

"""The governing-heading verdict for one item's assertions, as a shared value.

PURE. `SPECIFICATION/scenarios.md` Scenario 206's last scenario puts the remedy
for a non-governing citation on ONE authority — "the item is held with the
governing heading the spec-stated judgement returned as the remedy" — and
`contracts.md` section "Dispatcher admission, WIP cap, and post-merge
acceptance" makes that judgement a COMPONENT the Definition-of-Done judgement
consults rather than a replacement for it. So this module owns three things and
no decision about where they are spent: the behaviour STATEMENT the shared
judgement is asked about, the FINDINGS one returned verdict produces against a
reference line, and the BLOCK that carries the verdict into a subject a judge
reads.

WHY THE FOUR SURFACES SHARE ONE MODULE RATHER THAN ONE RULE EACH. The
filing-time advisory, the pre-admission judgement, the pre-dispatch judgement
and the `dod_gate` node each name the governing heading, and three of them name
it as a REMEDY an operator edits a reference line against. Four spellings of one
remedy is four edits a filer can make that satisfy one surface and not the next,
and nothing announces the divergence: every surface keeps producing a
well-formed finding.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

THE STATEMENT IS THE ASSERTIONS AS ONE BEHAVIOUR, never one statement per
assertion. `_ledger_intent_scan` records the same decision for the four intent
fields and for the same reason: a Definition of Done states ONE item's
behaviour, and judging each bullet alone reports `unstated` for behaviour its
siblings state. The item's title rides with them because a bullet is written
against the title it sits under and reads as a fragment without it.

A FINDING IS OWED FOR A GOVERNING HEADING THE REFERENCE LINE OMITS, AND FOR
NOTHING ELSE. Scenario 206's "names a heading that does not govern" and Scenario
239's "missing one of several governing headings" are the SAME observation from
two directions — a line that names a non-governing heading has necessarily
omitted the governing one — so one rule covers both and the remedy is the
heading the judgement returned. The mirror rule, refusing a reference the
judgement did not return, is deliberately absent: a non-scenario H2 "remains a
perfectly valid reference for an assertion no scenario states", and the
judgement answers about the assertions as a whole rather than per reference.

AN `unstated` VERDICT PRODUCES NO FINDING, which is the arm most easily read as
a gap. Its `stated_by` is empty by contract, so there is no heading to name, and
behaviour the ratified tree does not state is the SPEC-CHANGE TIER's business —
a finding here would tell a filer to cite a clause that does not exist.

A HEADING IS MATCHED ON ITS TITLE, with the optional `## ` marker stripped from
both sides. The reference line carries the marker by the section's own grammar
and `stated_by` carries it by the shared judgement's, so the two agree today;
normalizing is what keeps a filer who omitted the marker from being told to add
a heading their line already names, which is a remedy that cannot be carried
out.

AN ABSENT VERDICT RENDERS AN EXPLICIT ABSENCE RATHER THAN NOTHING. A subject
that simply omits the block leaves a judge unable to tell a verdict of "nothing
governs" from a judgement nobody took, and the two have opposite consequences:
the first forecloses the finding and the second leaves the node its own search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
        DefinitionOfDone,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "GOVERNING_HEADING_BLOCK_HEADING",
    "GOVERNING_HEADING_UNOBSERVED_BODY",
    "GoverningHeadingVerdict",
    "governing_heading_block",
    "governing_heading_findings",
    "governing_heading_statement",
]

# The subject block's own heading. PUBLIC because the `dod_gate` prompt names it
# verbatim so the node reads the verdict from the one place the Dispatcher
# writes it, and the prompt test binds that prose to this constant rather than
# to a second hand-typed copy.
GOVERNING_HEADING_BLOCK_HEADING = "## Governing-heading verdict (from the spec-stated judgement)"

# What stands where a verdict would be when none was taken. It NAMES the absence
# rather than leaving the block empty, for the reason the module docstring
# gives: a judge cannot otherwise tell "nothing governs" from "nobody asked".
GOVERNING_HEADING_UNOBSERVED_BODY = (
    "(no spec-stated judgement was taken for this item, so no governing-heading"
    " verdict is supplied and this check falls back on your own search)"
)

_KIND_FIELD = "kind"
_GOVERNING_FIELD = "governing heading"
_GENERALIZATION_FIELD = "generalization target"
_FIELD_SEPARATOR = ": "
_HEADING_MARKER = "## "
_STATEMENT_TITLE = "title"
_STATEMENT_ASSERTION = "asserts"
_UNSTATED_KIND = "unstated"


@dataclass(frozen=True, kw_only=True)
class GoverningHeadingVerdict:
    """One spec-stated judgement, reduced to what a governing-heading rule needs.

    A value of this package's own rather than `SpecStatedVerdict` itself, because
    the shared verdict carries a `rationale` that moves with the model's wording
    while naming the same clauses — and this value is rendered into the subject a
    reuse digest is taken over, so a field that moves without the verdict moving
    would retire every recorded verdict on a re-run that decided nothing new.
    """

    kind: str
    stated_by: tuple[str, ...] = ()
    generalization_target: str | None = None


def governing_heading_statement(*, item: WorkItem, section: DefinitionOfDone) -> str:
    """The ONE behaviour statement the spec-stated judgement is asked about.

    The item's title and every assertion of its section, rendered as one
    statement. A section carrying no assertion still renders its title, because
    the judgement's answer about an item with nothing to grade is still a fact
    about that item rather than a question nobody may ask.
    """
    lines = [f"{_STATEMENT_TITLE}{_FIELD_SEPARATOR}{item.title}"]
    lines.extend(
        f"{_STATEMENT_ASSERTION}{_FIELD_SEPARATOR}{assertion.text}"
        for assertion in section.assertions
    )
    return "\n".join(lines)


def governing_heading_findings(
    *, item: WorkItem, section: DefinitionOfDone, verdict: GoverningHeadingVerdict | None
) -> tuple[str, ...]:
    """One finding per governing heading this item's reference line omits.

    `None` yields nothing, which is the fail-open direction every surface here
    needs: a judgement that could not be taken is the absence of evidence that a
    citation does not govern, and a finding raised on it would hold an item for
    an outage no edit of the item can clear.
    """
    if verdict is None or verdict.kind == _UNSTATED_KIND:
        return ()
    named = {_title_of(heading=reference) for reference in section.references}
    return tuple(
        _omitted_heading_finding(item=item, heading=heading)
        for heading in verdict.stated_by
        if _title_of(heading=heading) not in named
    )


def governing_heading_block(*, verdict: GoverningHeadingVerdict | None) -> str:
    """The verdict as the subject and the goal carry it, absence included."""
    if verdict is None:
        return f"{GOVERNING_HEADING_BLOCK_HEADING}\n{GOVERNING_HEADING_UNOBSERVED_BODY}"
    lines = [GOVERNING_HEADING_BLOCK_HEADING, f"{_KIND_FIELD}{_FIELD_SEPARATOR}{verdict.kind}"]
    lines.extend(f"{_GOVERNING_FIELD}{_FIELD_SEPARATOR}{heading}" for heading in verdict.stated_by)
    if verdict.generalization_target is not None:
        lines.append(f"{_GENERALIZATION_FIELD}{_FIELD_SEPARATOR}{verdict.generalization_target}")
    return "\n".join(lines)


def _omitted_heading_finding(*, item: WorkItem, heading: str) -> str:
    return (
        f"work-item {item.id}: the Definition of Done reference line does not name"
        f" {heading!r}, which the spec-stated judgement returned as a clause governing"
        " this item's assertions; add that heading to the reference line verbatim, so"
        " the capture steps exercise the behaviour it states"
    )


def _title_of(*, heading: str) -> str:
    """One heading with its optional `## ` marker and surrounding space removed."""
    stripped = heading.strip()
    if stripped.startswith(_HEADING_MARKER):
        return stripped[len(_HEADING_MARKER) :].strip()
    return stripped

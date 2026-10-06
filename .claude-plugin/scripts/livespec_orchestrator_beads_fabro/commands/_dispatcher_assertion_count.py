"""The ONE assertion-count projection intake and terminal calibration share.

Plan slice S4 (`bd-ib-tbgxm4`) repairs the calibration `acceptance_count` size
proxy. The old derivation counted leading-bullet and Gherkin markers in the
item's DESCRIPTION, which is neither the text the acceptance evaluator grades
nor the number the filing display shows an operator, so the two ends of one
dispatch reported different counts and the analysis pass consumed the wrong
one. Measured on this repository's own journal (plan research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`):
the description regex read a MEDIAN OF ZERO on both the converged and the
non-converged side of 445 records, so the proxy carried no signal at all.

WHY THIS IS A MODULE RATHER THAN A CALL TO `effective_criteria` AT EACH END.
Both ends already COULD have called the sanctioned parser; the defect is that
one of them did not, and nothing structural stopped it. A projection both
consume makes the agreement a property of the code rather than of two call
sites that happen to match today — and it carries the SOURCE and the rendered
parse line beside the count, which a bare integer cannot.

WHY THE SOURCE RIDES WITH THE COUNT. A count alone cannot say WHICH text was
counted, and the three resolution steps are not equally trustworthy: a legacy
`criteria-field` or `description-exit-criteria` item declares no proof mode and
carries no Definition of Done section, which is exactly the population a
calibration reading should be able to separate out rather than average over. It
is the same value `parse_display()` names, so the record and the display cannot
disagree about provenance either.

This module is PURE: no IO, no environment reads, and it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
    effective_criteria,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "AssertionCount",
    "assertion_count_for",
    "assertion_count_of",
]


@dataclass(frozen=True, kw_only=True)
class AssertionCount:
    """One item's gradeable assertion count, its source, and the parse line.

    `parse_display` is `EffectiveCriteria.parse_display()` verbatim rather than
    a re-render: it is the line the capture, groom and approve displays already
    show, so a surface that reports this field reports exactly what the operator
    read at filing time — including the `definition-of-done: missing` marker a
    legacy source carries.
    """

    count: int
    source: str
    parse_display: str


def assertion_count_of(*, criteria: EffectiveCriteria) -> AssertionCount:
    """Project one ALREADY-RESOLVED effective-criteria set.

    The resolution-free entry point, for a caller that holds the resolved set
    for its own reasons — the filing display needs the assertions and their
    proof modes anyway. Resolving a second time there would read the same item
    twice and could not be shown to agree with the first read.
    """
    return AssertionCount(
        count=len(criteria.assertions),
        source=criteria.source,
        parse_display=criteria.parse_display(),
    )


def assertion_count_for(*, item: WorkItem) -> AssertionCount:
    """Resolve one item's effective criteria and project the count.

    The entry point for a caller that holds only the item — terminal
    calibration and the TDD order projection both do.
    """
    return assertion_count_of(criteria=effective_criteria(item=item))

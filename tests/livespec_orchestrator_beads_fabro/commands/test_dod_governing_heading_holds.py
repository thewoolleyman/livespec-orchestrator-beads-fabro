"""`governing_heading_holds`: an omission holds only when nothing cited governs.

The gate's fold-in and the repository preflight both decide hold-versus-advisory
by this one predicate (work-item `bd-ib-52zhw`). Each case varies one input, and
the two `stated` cases differ only in whether the cited heading is among the
governing ones, so they are each other's control.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_holds,
)

_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_OTHER = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_SECTION = definition_of_done(
    description=f"## Definition of Done\n\n- The omission is advisory.\n\nReferences: {_CITED}\n"
)


def test_a_line_naming_no_governing_heading_holds() -> None:
    verdict = GoverningHeadingVerdict(kind="stated", stated_by=(_OTHER,))

    assert governing_heading_holds(section=_SECTION, verdict=verdict) is True


def test_a_line_naming_one_governing_heading_does_not_hold() -> None:
    verdict = GoverningHeadingVerdict(kind="stated", stated_by=(_CITED, _OTHER))

    assert governing_heading_holds(section=_SECTION, verdict=verdict) is False


def test_a_judgement_that_could_not_be_taken_does_not_hold() -> None:
    assert governing_heading_holds(section=_SECTION, verdict=None) is False


def test_an_unstated_verdict_does_not_hold() -> None:
    verdict = GoverningHeadingVerdict(kind="unstated", stated_by=())

    assert governing_heading_holds(section=_SECTION, verdict=verdict) is False


def test_a_verdict_naming_no_heading_does_not_hold() -> None:
    verdict = GoverningHeadingVerdict(kind="partial", stated_by=())

    assert governing_heading_holds(section=_SECTION, verdict=verdict) is False

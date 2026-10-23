"""Tests for the governing-heading verdict the four citation checks share.

`SPECIFICATION/scenarios.md` Scenario 206's last scenario gives the remedy for a
non-governing citation ONE authority — "the item is held with the governing
heading the spec-stated judgement returned as the remedy" — and Scenario 239
asks every host taking to refuse "a reference line missing one of several
governing headings ... naming the omitted scenario heading and that H2
verbatim, each with the remedy of adding it".

THE LOAD-BEARING CASES ARE THE TWO ABSENCES. A verdict that could not be taken
must yield NO finding, because an outage is not evidence that a citation fails
to govern and there is no edit an operator could make to clear it; and an
`unstated` verdict must yield no finding either, because its `stated_by` is
empty by contract and behaviour the ratified tree does not state is the
spec-change tier's business rather than a reference-line defect.

THE MARKER-LESS CITATION CASE IS THE OTHER ONE WORTH KEEPING. A filer who wrote
the heading without its `## ` marker has named the governing heading, so a rule
comparing raw strings tells them to add a heading their line already carries —
a remedy that cannot be carried out, which is worse than no finding.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from types import ModuleType

_MODULE = "livespec_orchestrator_beads_fabro.commands._dod_governing_heading"
_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dod_governing_heading.py"
)

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_OTHER_GOVERNING = "## Dispatcher admission, WIP cap, and post-merge acceptance"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"

_FIRST_ASSERTION = "The citation checks consult the spec-stated judgement before admission."
_SECOND_ASSERTION = "A refused item re-enters enumeration once its digests differ."


def _item(*, description: str | None = None) -> WorkItem:
    return WorkItem(
        id="bd-ib-m76p2n",
        type="feature",
        status="ready",
        title="The citation checks consult the spec-stated judgement",
        description=(
            f"## Definition of Done\n\n- {_FIRST_ASSERTION}\n- {_SECOND_ASSERTION}\n\n"
            f"References: {_CITED}\n"
            if description is None
            else description
        ),
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _module() -> ModuleType:
    return importlib.import_module(_MODULE)


def _verdict(module: ModuleType, **fields: Any) -> Any:
    return module.GoverningHeadingVerdict(**fields)


def test_the_module_that_owns_the_shared_governing_heading_verdict_exists() -> None:
    assert _MODULE_PATH.is_file(), (
        "the four citation checks share one governing-heading verdict, so the"
        " statement, the findings and the subject block live in one module"
    )


def test_an_omitted_governing_heading_is_a_finding_naming_it_and_the_remedy() -> None:
    module = _module()
    item = _item()

    findings = module.governing_heading_findings(
        item=item,
        section=definition_of_done(description=item.description),
        verdict=_verdict(module, kind="stated", stated_by=(_GOVERNING, _OTHER_GOVERNING)),
    )

    assert len(findings) == 2
    assert _GOVERNING in findings[0]
    assert _OTHER_GOVERNING in findings[1]
    for finding in findings:
        assert item.id in finding
        assert "add that heading to the reference line" in finding


def test_a_governing_heading_the_reference_line_already_names_is_no_finding() -> None:
    module = _module()
    item = _item()

    findings = module.governing_heading_findings(
        item=item,
        section=definition_of_done(description=item.description),
        verdict=_verdict(module, kind="stated", stated_by=(_CITED,)),
    )

    assert findings == ()


def test_a_marker_less_citation_still_matches_the_heading_the_judgement_returned() -> None:
    module = _module()
    bare = _CITED.removeprefix("## ")
    item = _item(
        description=f"## Definition of Done\n\n- {_FIRST_ASSERTION}\n\nReferences: {bare}\n"
    )

    findings = module.governing_heading_findings(
        item=item,
        section=definition_of_done(description=item.description),
        verdict=_verdict(module, kind="stated", stated_by=(_CITED,)),
    )

    assert findings == ()


def test_an_unobserved_or_unstated_verdict_raises_no_finding() -> None:
    module = _module()
    item = _item()
    section = definition_of_done(description=item.description)

    assert module.governing_heading_findings(item=item, section=section, verdict=None) == ()
    assert (
        module.governing_heading_findings(
            item=item,
            section=section,
            verdict=_verdict(module, kind="unstated", stated_by=()),
        )
        == ()
    )


def test_the_statement_the_judgement_grades_is_the_title_and_every_assertion() -> None:
    module = _module()
    item = _item()

    statement = module.governing_heading_statement(
        item=item, section=definition_of_done(description=item.description)
    )

    assert item.title in statement
    assert _FIRST_ASSERTION in statement
    assert _SECOND_ASSERTION in statement


def test_the_subject_block_carries_every_returned_heading_and_names_an_absence() -> None:
    module = _module()

    rendered = module.governing_heading_block(
        verdict=_verdict(
            module,
            kind="partial",
            stated_by=(_GOVERNING,),
            generalization_target=_OTHER_GOVERNING,
        )
    )

    assert module.GOVERNING_HEADING_BLOCK_HEADING in rendered
    assert "partial" in rendered
    assert _GOVERNING in rendered
    assert _OTHER_GOVERNING in rendered

    absent = module.governing_heading_block(verdict=None)

    assert module.GOVERNING_HEADING_BLOCK_HEADING in absent
    assert module.GOVERNING_HEADING_UNOBSERVED_BODY in absent

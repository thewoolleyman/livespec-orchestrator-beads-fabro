"""Tests that ANY Definition of Done change invalidates a governing-heading verdict.

The contract says a change to the item's Definition of Done changes the
verdict's input. A digest built from a list of the section's PARTS is blind to
every part it does not list: the first fix listed the proof modes and the
reference line, and an independent confirmation review then changed only a
`Reason:` line and saw the old verdict reused. So the input carries the
section's own text, and these cases change one part each.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"
_ATTESTED = (
    "## Definition of Done\n\n### Human-attested\n\n"
    "Reason: no agent session can observe it.\n\n"
    "- The judgement runs before admission.\n\n"
    f"References: {_HEADING}\n"
)


def _item(*, description: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="ready",
        title="Judge before admission",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


@pytest.mark.parametrize(
    "edited",
    [
        _ATTESTED.replace(
            "no agent session can observe it.", "the operator must confirm the external audit."
        ),
        _ATTESTED.replace("### Human-attested", "### Host-captured"),
        _ATTESTED.replace(_HEADING, "## Scenario 175 — Another heading"),
        _ATTESTED.replace(f"References: {_HEADING}", f"References: {_HEADING}  "),
        _ATTESTED.replace("## Definition of Done", "# Definition of Done"),
        _ATTESTED.replace("observe it.\n", "observe it.\r\n"),
        _ATTESTED.replace("observe it.\n", "observe it.\v"),
    ],
)
def test_a_definition_of_done_edit_outside_the_assertion_text_changes_the_input(
    edited: str,
) -> None:
    before = governing_heading_subject_digest(item=_item(description=_ATTESTED), comments=())

    after = governing_heading_subject_digest(item=_item(description=edited), comments=())

    assert after != before


def test_text_outside_the_section_does_not_change_the_input() -> None:
    """Carrier prose after the section is not the Definition of Done."""
    item = _item(description=_ATTESTED)
    trailing = replace(item, description=_ATTESTED + "\n## Notes\n\nUnrelated prose.\n")

    assert governing_heading_subject_digest(
        item=trailing, comments=()
    ) == governing_heading_subject_digest(item=item, comments=())


def test_the_section_source_is_its_body_and_empty_without_a_section() -> None:
    assert "Reason: no agent session can observe it." in definition_of_done_source(
        description=_ATTESTED
    )
    assert definition_of_done_source(description="## Definition of Done\n\n") != ""
    assert definition_of_done_source(description="## Something else\n\n- x.\n") == ""
    assert definition_of_done_source(description="no heading at all") == ""

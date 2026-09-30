"""Tests for the Definition of Done section as the first criteria source (v114).

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md` makes
the description's Definition of Done section resolution step 1, ahead of the two
legacy sources, and names the resolved source `description-definition-of-done`.
The source name is asserted as a LITERAL rather than through the module's
constant: it is a ratified wire value that a display and an operator read, so a
test that imports the constant would follow a rename that broke both.

The position tests are the load-bearing ones. The clause requires the section as
the description's FIRST heading, so the discriminating case is a description
whose first heading is something else while a LATER heading is titled
`Definition of Done` — a parse that merely searched for a matching heading would
accept it, and every such description would then carry a definition that sits
outside the position the gate and the human both read.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_DEFINITION_OF_DONE = (
    "## Definition of Done\n"
    "\n"
    "- The wall refuses an item whose section is absent.\n"
    "- The refusal names the offending element of the section.\n"
    "\n"
    "References: ## Effective acceptance criteria\n"
)
_LEGACY_FIELD = "The legacy criteria field carries one assertion.\n"
_MIXED_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The factory captures this one.\n"
    "\n"
    "### Human-attested\n"
    "\n"
    "Reason: the proof needs a session on an external administrative console.\n"
    "\n"
    "- A human attests this one.\n"
    "\n"
    "References: ## Effective acceptance criteria\n"
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-v114",
        type="task",
        status="ready",
        title="A gated task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def test_the_definition_of_done_section_wins_over_the_legacy_criteria_field() -> None:
    # Step 1 beats step 2: an item carrying BOTH a Definition of Done section
    # and a gradeable native field resolves from the section, which is the whole
    # content of "the Definition of Done section is resolution step 1".
    resolved = effective_criteria(
        item=_item(description=_DEFINITION_OF_DONE, acceptance_criteria=_LEGACY_FIELD)
    )

    assert resolved.source == "description-definition-of-done"
    assert resolved.assertions == (
        "The wall refuses an item whose section is absent.",
        "The refusal names the offending element of the section.",
    )


def test_the_reference_line_is_not_a_gradeable_assertion() -> None:
    # The clause forbids counting it, and the control is that the section's two
    # bullets DO survive — a parse that dropped everything would pass an
    # assertion count check while carrying no criteria at all.
    section = definition_of_done(description=_DEFINITION_OF_DONE)

    assert section.present is True
    assert section.criteria_text is not None
    assert "References:" not in section.criteria_text


def test_a_description_with_no_heading_carries_no_section() -> None:
    section = definition_of_done(description="Do the thing.\n")

    assert section.present is False
    assert section.criteria_text is None


def test_a_later_definition_of_done_heading_does_not_satisfy_the_first_position() -> None:
    # The discriminating case for "as its FIRST heading". A search-anywhere parse
    # accepts this description; the ratified parse does not.
    description = (
        "## Context\n"
        "\n"
        "Some prose.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        "- The section is in the wrong position.\n"
    )

    section = definition_of_done(description=description)

    assert section.present is False
    assert section.criteria_text is None


def test_prose_before_the_heading_is_allowed_and_a_sibling_heading_ends_the_section() -> None:
    # The clause permits prose ahead of the heading, and the section ends at the
    # next heading of its own level or above — so `## Context`'s bullet must not
    # be graded as part of the Definition of Done.
    description = (
        "Some prose first.\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        "- The section body is the bullets under the heading.\n"
        "\n"
        "## Context\n"
        "\n"
        "- This bullet belongs to Context and is not an assertion.\n"
    )

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.source == "description-definition-of-done"
    assert resolved.assertions == ("The section body is the bullets under the heading.",)


def test_a_sub_heading_inside_the_section_is_not_an_assertion() -> None:
    # `### Human-attested` is neither short-and-shouting nor colon-terminated, so
    # the shared segmenter's header heuristic reads it as prose. Excluding
    # heading lines here is what keeps it out of the gradeable set.
    description = (
        "## Definition of Done\n"
        "\n"
        "- The factory captures this one.\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.assertions == (
        "The factory captures this one.",
        "A human attests this one.",
    )


def test_a_present_but_empty_section_falls_through_to_the_legacy_field() -> None:
    # A heading with nothing gradeable under it is not a criteria source, so
    # resolution continues rather than reporting an empty step-1 result.
    description = "## Definition of Done\n\nReferences: ## Effective acceptance criteria\n"

    section = definition_of_done(description=description)
    resolved = effective_criteria(
        item=_item(description=description, acceptance_criteria=_LEGACY_FIELD)
    )

    assert section.present is True
    assert section.criteria_text is None
    assert resolved.source == "criteria-field"


# --- per-assertion proof mode ------------------------------------------------


def test_the_reason_line_is_not_a_gradeable_assertion() -> None:
    # The `Reason:` line is required PROSE, not an assertion. It is flush-left,
    # is not a heading and is not the reference line, so nothing in the shared
    # segmenter's own rules would keep it out of the gradeable set.
    resolved = effective_criteria(item=_item(description=_MIXED_SECTION))

    assert resolved.assertions == (
        "The factory captures this one.",
        "A human attests this one.",
    )


def test_each_assertion_carries_the_mode_its_position_declares() -> None:
    # The default is the STRICT case: an assertion is `factory_captured` unless
    # it sits under a `### Human-attested` sub-heading. The modes are parallel to
    # the assertions and in the section's own order, because the proof record and
    # the acceptance evidence leg both index one against the other.
    resolved = effective_criteria(item=_item(description=_MIXED_SECTION))

    assert resolved.proof_modes == ("factory_captured", "human_attested")


def test_a_legacy_source_declares_no_proof_mode_at_all() -> None:
    # An item resolved from a legacy source carries no mode declarations, which
    # is DISTINCT from declaring every assertion `factory_captured`: the
    # acceptance pass keeps grading a legacy item by merged-diff vocabulary and
    # must be able to tell the two apart.
    resolved = effective_criteria(item=_item(acceptance_criteria=_LEGACY_FIELD))

    assert resolved.source == "criteria-field"
    assert resolved.assertions != ()
    assert resolved.proof_modes == ()


def test_a_well_formed_human_attested_sub_heading_is_not_malformed() -> None:
    section = definition_of_done(description=_MIXED_SECTION)

    assert section.malformed_proof_modes == ()
    assert section.human_attested_assertions == ("A human attests this one.",)


def test_a_human_attested_sub_heading_with_no_reason_line_is_malformed() -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "- The factory captures this one.\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    section = definition_of_done(description=description)

    assert section.malformed_proof_modes == ("Human-attested",)
    # The assertion itself still parses and still carries the human mode: the
    # sub-heading is malformed, not absent, and a wall that silently downgraded
    # the mode would let the item auto-close without the human leg.
    assert section.human_attested_assertions == ("A human attests this one.",)


def test_a_reason_line_with_no_text_is_no_reason_line() -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "Reason:\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    assert definition_of_done(description=description).malformed_proof_modes == ("Human-attested",)


def test_a_sub_heading_that_is_not_human_attested_returns_the_mode_to_the_default() -> None:
    # Only `### Human-attested` opts out. Any other sub-heading is ordinary
    # grouping, needs no `Reason:` line, and its bullets are factory-captured —
    # otherwise a section could opt out of mechanical proof by accident.
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "Reason: the proof needs a physical device.\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        "### Host walls\n"
        "\n"
        "- The factory captures this one.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    section = definition_of_done(description=description)

    assert section.malformed_proof_modes == ()
    # Read through the attributes rather than the dataclass so the assertion
    # names the two facts under test — text and mode, in section order.
    assert [(one.text, one.proof_mode) for one in section.assertions] == [
        ("A human attests this one.", "human_attested"),
        ("The factory captures this one.", "factory_captured"),
    ]

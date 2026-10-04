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
# All three modes in one section, in the order the v115 enumeration orders them.
# A section carrying only two of them cannot tell a parse that maps each
# sub-heading to its OWN mode from one that maps every opt-out sub-heading to the
# single mode it already knew about.
_THREE_MODE_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The factory captures this one.\n"
    "\n"
    "### Host-captured\n"
    "\n"
    "Reason: the proof needs the released build installed on an operator host.\n"
    "\n"
    "- An agent session captures this one on a host.\n"
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


def test_a_host_captured_sub_heading_declares_the_host_mode_for_its_bullets() -> None:
    # The v115 third mode. The control is the FACTORY-captured bullet above the
    # sub-heading: a parse that declared the whole section host-captured would
    # satisfy a check on the host bullet alone, and the item would then rest for a
    # host leg that two of its three assertions never needed.
    section = definition_of_done(description=_THREE_MODE_SECTION)

    assert [(one.text, one.proof_mode) for one in section.assertions] == [
        ("The factory captures this one.", "factory_captured"),
        ("An agent session captures this one on a host.", "host_captured"),
        ("A human attests this one.", "human_attested"),
    ]
    assert section.host_captured_assertions == ("An agent session captures this one on a host.",)
    assert section.human_attested_assertions == ("A human attests this one.",)
    # A well-formed `Reason:` line under EITHER opt-out sub-heading clears the
    # malformed finding, which is what makes the refusal below evidence of the
    # missing line rather than of the sub-heading's mere presence.
    assert section.malformed_proof_modes == ()


def test_the_host_captured_mode_reaches_the_effective_criteria_primitive() -> None:
    # The parse is consumed through the ONE criteria primitive, never directly, so
    # a mode that stops at the section parse reaches no wall and no acceptance
    # pass. `proof_modes` is parallel to `assertions` in section order.
    resolved = effective_criteria(item=_item(description=_THREE_MODE_SECTION))

    assert resolved.proof_modes == ("factory_captured", "host_captured", "human_attested")
    assert resolved.host_captured_assertions == ("An agent session captures this one on a host.",)
    # The two legs the AI pass never grades, in section order. The completion
    # disposition reads exactly this to decide that a PASS may not close.
    assert resolved.pending_leg_assertions == (
        "An agent session captures this one on a host.",
        "A human attests this one.",
    )


def test_a_host_captured_sub_heading_with_no_reason_line_is_malformed() -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "- The factory captures this one.\n"
        "\n"
        "### Host-captured\n"
        "\n"
        "- An agent session captures this one on a host.\n"
        "\n"
        "References: ## Effective acceptance criteria\n"
    )

    section = definition_of_done(description=description)

    assert section.malformed_proof_modes == ("Host-captured",)
    # The assertion still carries the host mode: the declaration is malformed, not
    # absent, and silently downgrading it would let the item auto-close with no
    # host leg at all — the one outcome the sub-heading exists to prevent.
    assert section.host_captured_assertions == ("An agent session captures this one on a host.",)


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


# --- the parse display: the legacy-source gap is reported, not silent ---------


def test_the_parse_display_reports_the_gap_for_a_legacy_criteria_field() -> None:
    # The capture, groom and approve displays all render `parse_display()`, and
    # the clause requires an item resolved from a LEGACY source to be reported as
    # `definition-of-done: missing` so the gap is repaired when it is next
    # touched. Without the marker the display reads as a clean parse: it reports
    # a positive assertion count from a source the walls will refuse.
    resolved = effective_criteria(item=_item(acceptance_criteria=_LEGACY_FIELD))

    assert resolved.source == "criteria-field"
    assert "definition-of-done: missing" in resolved.parse_display()


def test_the_parse_display_reports_the_gap_for_a_legacy_exit_criteria_section() -> None:
    description = "## Exit criteria\n\nThe legacy section carries one assertion.\n"

    resolved = effective_criteria(item=_item(description=description))

    assert resolved.source == "description-exit-criteria"
    assert "definition-of-done: missing" in resolved.parse_display()


def test_the_parse_display_reports_no_gap_for_a_definition_of_done_source() -> None:
    # The control. A marker printed unconditionally would carry no information —
    # every item would report the gap, including the conforming ones.
    #
    # The needle is the WHOLE marker, not a bare `definition-of-done`: the
    # conforming source is NAMED `description-definition-of-done`, so a probe on
    # the shorter form matches the source name itself and could never return the
    # answer this control asks for.
    resolved = effective_criteria(item=_item(description=_DEFINITION_OF_DONE))

    assert resolved.source == "description-definition-of-done"
    assert "definition-of-done: missing" not in resolved.parse_display()
    # The parse itself is unchanged: the marker is ADDED to the existing line,
    # never a replacement for the count and source the displays already show.
    assert "2 gradeable assertion(s)" in resolved.parse_display()

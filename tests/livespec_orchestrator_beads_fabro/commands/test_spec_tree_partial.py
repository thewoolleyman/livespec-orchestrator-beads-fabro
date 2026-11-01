"""Partial section rendering remains marked and budget-bounded."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    partially_selected_section,
)


def test_a_partial_section_keeps_its_leading_body_and_marks_the_remainder() -> None:
    rendered = partially_selected_section(
        heading="## Governing section",
        body="\n\nThe leading governing detail is retained. " * 100,
        full="",
        elided="## Governing section\n(body omitted)\n",
        remaining=1_000,
    )

    assert rendered is not None
    assert rendered.startswith("## Governing section\n\nThe leading governing detail")
    assert "partially withheld" in rendered


def test_a_partial_section_requires_room_for_text_and_a_nonempty_body() -> None:
    assert (
        partially_selected_section(
            heading="## Governing section",
            body="\n",
            full="",
            elided="## Governing section\n(body omitted)\n",
            remaining=1_000,
        )
        is None
    )
    assert (
        partially_selected_section(
            heading=None,
            body="",
            full="Preamble body",
            elided="(body omitted)\n",
            remaining=0,
        )
        is None
    )

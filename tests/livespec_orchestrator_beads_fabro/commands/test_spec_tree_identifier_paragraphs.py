"""Selection and rendering of paragraphs that name a statement's backticked literals."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    condensed_spec_tree,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_identifier_paragraphs import (
    identified_paragraphs,
    merged_selection,
    section_with_paragraphs,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    PARTIALLY_WITHHELD_BODY_MARKER,
)

_HEADING = "## A contract"
_ONE = "Runs `tool run-one` today."
_TWO = "Runs `tool run-one` and writes `marker-line-two`."
_OTHER = "Prose with no literal."


@dataclass(frozen=True, kw_only=True)
class _Section:
    key: tuple[str, int]
    heading: str | None
    body: str
    full: str
    elided: str = "elided\n"


def _section(*, index: int = 1, body: str, heading: str | None = _HEADING) -> _Section:
    return _Section(
        key=("contracts.md", index),
        heading=heading,
        body=body,
        full=f"{heading}{body}" if heading is not None else body,
    )


def test_no_backticked_literal_in_the_statement_retains_nothing() -> None:
    sections = [_section(body=f"\n\n{_ONE}")]

    assert identified_paragraphs(
        sections=sections, asked_text="Runs tool run-one.", remaining=999
    ) == (
        {},
        999,
    )


def test_a_literal_without_a_separator_or_below_the_minimum_length_is_ignored() -> None:
    sections = [_section(body=f"\n\n{_ONE}\n\nA `short` word, and a `plainliteral` word.")]

    asked = "Uses `short` and `plainliteral` and `a-b`."

    assert identified_paragraphs(sections=sections, asked_text=asked, remaining=999) == ({}, 999)


def test_paragraphs_are_ranked_by_literals_named_and_held_to_a_share_of_the_budget() -> None:
    sections = [_section(body=f"\n\n{_ONE}\n\n{_OTHER}\n\n{_TWO}")]
    asked = "Runs `tool run-one` and writes `marker-line-two`."
    first_cost = len(f"\n\n{_TWO}") + len(_HEADING) + len(PARTIALLY_WITHHELD_BODY_MARKER) - 7

    retained, left = identified_paragraphs(sections=sections, asked_text=asked, remaining=40_000)
    tight, tight_left = identified_paragraphs(
        sections=sections, asked_text=asked, remaining=4 * first_cost
    )

    assert retained == {("contracts.md", 1): ((1, f"\n\n{_ONE}"), (3, f"\n\n{_TWO}"))}
    assert left < 40_000
    assert tight == {("contracts.md", 1): ((3, f"\n\n{_TWO}"),)}
    assert tight_left == 3 * first_cost


def test_a_preamble_paragraph_is_read_from_the_whole_section() -> None:
    sections = [_section(index=0, heading=None, body=f"{_ONE}\n\n{_OTHER}")]

    retained, _left = identified_paragraphs(
        sections=sections, asked_text="Runs `tool run-one`.", remaining=40_000
    )

    assert retained == {("contracts.md", 0): ((0, _ONE),)}


def test_a_section_is_rendered_partial_with_the_retained_paragraph_and_marker() -> None:
    section = _section(body=f"\n\n{_ONE}\n\n{_OTHER}")

    rendered = section_with_paragraphs(
        section=section, current=None, paragraphs=[(1, f"\n\n{_ONE}")]
    )

    assert rendered == f"{_HEADING}\n\n{_ONE}{PARTIALLY_WITHHELD_BODY_MARKER}"


def test_a_partial_selection_gains_only_the_paragraphs_it_lacks() -> None:
    section = _section(body=f"\n\n{_OTHER}\n\n{_ONE}\n\n{_TWO}")
    current = f"{_HEADING}\n\n{_OTHER}{PARTIALLY_WITHHELD_BODY_MARKER}"

    rendered = section_with_paragraphs(
        section=section,
        current=current,
        paragraphs=[(2, f"\n\n{_ONE}"), (3, f"\n\n{_OTHER}")],
    )

    assert rendered == f"{_HEADING}\n\n{_OTHER}\n\n{_ONE}{PARTIALLY_WITHHELD_BODY_MARKER}"


def test_retaining_every_paragraph_renders_the_whole_section_without_a_marker() -> None:
    section = _section(body=f"\n\n{_ONE}")
    preamble = _section(index=0, heading=None, body=_ONE)

    assert section_with_paragraphs(
        section=section, current=None, paragraphs=[(1, f"\n\n{_ONE}")]
    ) == (section.full)
    assert section_with_paragraphs(section=preamble, current=None, paragraphs=[(0, _ONE)]) == _ONE


def test_a_cited_section_keeps_its_stating_paragraph_beside_its_leading_text() -> None:
    stating = "The `tool run-one` command MUST write `marker-line-two` first."
    tree = {
        "contracts.md": f"{_HEADING}\n\n" + "background filler.\n\n" * 15_000 + stating + "\n",
    }
    statement = (
        f"## Definition of Done\n\nReferences: {_HEADING}\n\n"
        "- The `tool run-one` command writes `marker-line-two`.\n"
    )

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=40_000)

    assert stating in condensed["contracts.md"]


def test_a_whole_section_is_kept_whole_when_it_is_already_complete() -> None:
    section = _section(body=f"\n\n{_ONE}\n\n{_OTHER}")

    merged = merged_selection(
        sections=[section],
        selected={section.key: section.full},
        complete={section.key},
        identified={section.key: [(1, f"\n\n{_ONE}")]},
    )

    assert merged == {section.key: section.full}

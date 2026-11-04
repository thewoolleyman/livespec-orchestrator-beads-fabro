"""Reference-overflow allocation keeps cited evidence fair and deterministic."""

from __future__ import annotations

import re

from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    partially_selected_section,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_referenced_selection import (
    ReferencedSection,
    select_referenced_sections,
)

_TERM = re.compile(r"[a-z0-9_]{3,}")


def _section(*, index: int, body: str) -> ReferencedSection:
    heading = f"## Cited section {index}"
    full = f"{heading}{body}"
    return ReferencedSection(
        key=("contracts.md", index),
        heading=heading,
        body=body,
        full=full,
        elided=f"{heading}\n(body omitted)\n",
        terms=frozenset(_TERM.findall(full.casefold())),
    )


def test_references_that_fit_stay_complete() -> None:
    """A non-overflowed cited set remains complete and records its keys."""
    sections = [_section(index=1, body="\n\nalpha detail\n")]

    selected, complete, _ = select_referenced_sections(
        sections=sections,
        terms=frozenset({"alpha"}),
        remaining=1_000,
    )

    assert selected == {sections[0].key: sections[0].full}
    assert complete == {sections[0].key}


def test_overflowed_references_each_receive_their_relevant_paragraph() -> None:
    """Equal shares protect a second cited section from the first one's prefix."""
    first = _section(index=1, body="\n\nleading text " * 500 + "\n\nalpha evidence\n")
    second = _section(index=2, body="\n\nbackground text " * 500 + "\n\nbravo evidence\n")

    selected, complete, _ = select_referenced_sections(
        sections=[first, second],
        terms=frozenset({"alpha", "bravo"}),
        remaining=2_000,
    )

    assert "alpha evidence" in selected[first.key]
    assert "bravo evidence" in selected[second.key]
    assert "leading text \n\nleading text" not in selected[first.key]
    assert "background text \n\nbackground text" not in selected[second.key]
    assert complete == set()


def test_no_fitting_relevant_paragraph_uses_the_existing_leading_fallback() -> None:
    """A single oversized relevant paragraph retains the previous useful prefix."""
    section = _section(index=1, body="\n\nalpha evidence " * 1_000)

    selected, complete, _ = select_referenced_sections(
        sections=[section],
        terms=frozenset({"alpha"}),
        remaining=500,
    )

    assert selected[section.key].startswith("## Cited section 1\n\nalpha evidence")
    assert complete == set()


def test_affordable_cited_evidence_is_redistributed_before_a_larger_selection() -> None:
    """An affordable cited match frees its unused share for the other citation."""
    small = _section(
        index=1,
        body="\n\nbackground text " * 100 + "\n\nalpha evidence\n",
    )
    large = _section(index=2, body="\n\nbravo evidence " * 100)

    selected, complete, _ = select_referenced_sections(
        sections=[small, large],
        terms=frozenset({"alpha", "bravo"}),
        remaining=400,
    )

    assert "alpha evidence" in selected[small.key]
    assert "bravo evidence" in selected[large.key]
    assert complete == set()


def test_fallback_keeps_a_whole_citation_before_partially_rendering_the_next() -> None:
    """The legacy fallback records a whole cited section when it fits."""
    first = _section(index=1, body="\n\nfirst leading text\n")
    second = _section(index=2, body="\n\nsecond leading text " * 100)

    selected, complete, _ = select_referenced_sections(
        sections=[first, second],
        terms=frozenset({"unmatched"}),
        remaining=200,
    )

    assert selected[first.key] == first.full
    assert selected[second.key].startswith("## Cited section 2")
    assert complete == {first.key}


def test_too_small_a_share_falls_back_when_relevant_evidence_cannot_be_marked() -> None:
    """A relevance match still falls back if its allotted share cannot mark it."""
    first = _section(
        index=1,
        body="\n\nbackground text " * 100 + "\n\nalpha evidence\n",
    )
    second = _section(
        index=2,
        body="\n\nbackground text " * 100 + "\n\nbravo evidence\n",
    )

    selected, complete, _ = select_referenced_sections(
        sections=[first, second],
        terms=frozenset({"alpha", "bravo"}),
        remaining=200,
    )

    assert selected[first.key].startswith("## Cited section 1")
    assert second.key not in selected
    assert complete == set()


def test_fallback_omits_a_citation_when_no_budget_remains_for_its_marker() -> None:
    """A cited heading alone remains when a preceding whole citation spends the budget."""
    first = _section(index=1, body="\n\nfirst leading text\n")
    second = _section(index=2, body="\n\nsecond leading text " * 100)
    first_cost = len(first.full) - len(first.elided)

    selected, complete, remaining = select_referenced_sections(
        sections=[first, second],
        terms=frozenset({"unmatched"}),
        remaining=first_cost,
    )

    assert selected == {first.key: first.full}
    assert complete == {first.key}
    assert remaining == 0


def test_a_relevant_selection_that_carries_the_whole_body_returns_the_full_section() -> None:
    """A marker never replaces a body the available budget can carry whole."""
    full = "## Cited section\n\nalpha evidence\n\nalpha more evidence\n"

    rendered = partially_selected_section(
        heading="## Cited section",
        body=full.removeprefix("## Cited section"),
        full=full,
        elided="## Cited section\n(body omitted)\n",
        remaining=1_000,
        terms=frozenset({"alpha"}),
    )

    assert rendered == full

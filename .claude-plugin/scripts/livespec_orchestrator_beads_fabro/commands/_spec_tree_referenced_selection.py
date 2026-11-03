"""Fair, relevance-first selection for cited specification sections."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    partially_selected_section,
)

__all__: list[str] = ["ReferencedSection", "select_referenced_sections"]


@dataclass(frozen=True, kw_only=True)
class ReferencedSection:
    """The rendering inputs and identity of one cited specification section."""

    key: tuple[str, int]
    heading: str | None
    body: str
    full: str
    elided: str
    terms: frozenset[str]


def select_referenced_sections(
    *,
    sections: list[ReferencedSection],
    terms: frozenset[str],
    remaining: int,
) -> tuple[dict[tuple[str, int], str], set[tuple[str, int]], int]:
    """Spend an overflowed reference budget fairly on each section's relevant prose."""
    total_cost = sum(len(section.full) - len(section.elided) for section in sections)
    if total_cost <= remaining:
        return (
            {section.key: section.full for section in sections},
            {section.key for section in sections},
            remaining - total_cost,
        )
    selected, remaining = _fair_partials(sections=sections, terms=terms, remaining=remaining)
    if selected:
        return selected, set(), remaining
    return _leading_sections(sections=sections, remaining=remaining)


def _fair_partials(
    *,
    sections: list[ReferencedSection],
    terms: frozenset[str],
    remaining: int,
) -> tuple[dict[tuple[str, int], str], int]:
    """Allocate equal shares, redistributing a cited section's unused share."""
    candidates = [
        (section, partial)
        for section in sections
        if (
            partial := partially_selected_section(
                heading=section.heading,
                body=section.body,
                full=section.full,
                elided=section.elided,
                remaining=len(section.full),
                terms=section.terms & terms,
            )
        )
        is not None
    ]
    selected: dict[tuple[str, int], str] = {}
    while candidates and remaining > 0:
        share = remaining // len(candidates)
        affordable = [
            candidate
            for candidate in candidates
            if len(candidate[1]) - len(candidate[0].elided) <= share
        ]
        if affordable:
            for section, partial in affordable:
                selected[section.key] = partial
                remaining -= len(partial) - len(section.elided)
            candidates = [candidate for candidate in candidates if candidate not in affordable]
            continue
        for section, _ in candidates:
            partial = partially_selected_section(
                heading=section.heading,
                body=section.body,
                full=section.full,
                elided=section.elided,
                remaining=share,
                terms=section.terms & terms,
            )
            if partial is not None:
                selected[section.key] = partial
                remaining -= len(partial) - len(section.elided)
        break
    return selected, remaining


def _leading_sections(
    *, sections: list[ReferencedSection], remaining: int
) -> tuple[dict[tuple[str, int], str], set[tuple[str, int]], int]:
    """Retain leading text when no relevant paragraph fits any cited section."""
    selected: dict[tuple[str, int], str] = {}
    complete: set[tuple[str, int]] = set()
    for section in sections:
        cost = len(section.full) - len(section.elided)
        if cost <= remaining:
            selected[section.key] = section.full
            complete.add(section.key)
            remaining -= cost
            continue
        partial = partially_selected_section(
            heading=section.heading,
            body=section.body,
            full=section.full,
            elided=section.elided,
            remaining=remaining,
        )
        if partial is not None:
            selected[section.key] = partial
            remaining -= len(partial) - len(section.elided)
    return selected, complete, remaining

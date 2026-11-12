"""Reserve prompt budget for paragraphs that directly match the asked behaviour."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Protocol, TypeVar

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
    reference_line_headings,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    PARAGRAPH,
    PARTIALLY_WITHHELD_BODY_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_scenario_governing import (
    pinned_sections,
)

__all__: list[str] = [
    "combine_paragraphs",
    "pinned_sections_for_statement",
    "reserve_relevant_paragraphs",
    "select_by_relevance",
]

_SHARE = 4
_TERM = re.compile(r"[a-z0-9_]{3,}")


class RelevantSection(Protocol):
    """The section fields needed to retain a matching paragraph."""

    @property
    def key(self) -> tuple[str, int]: ...

    @property
    def path(self) -> str: ...

    @property
    def heading(self) -> str | None: ...

    @property
    def body(self) -> str: ...

    @property
    def full(self) -> str: ...

    @property
    def elided(self) -> str: ...


SectionT = TypeVar("SectionT", bound=RelevantSection)


def pinned_sections_for_statement(
    *,
    sections: Sequence[SectionT],
    statement: str,
    spec_tree: Mapping[str, str],
    term_pattern: re.Pattern[str],
) -> tuple[list[SectionT], frozenset[str]]:
    """Return references and governing terms that the stated behaviour makes mandatory."""
    definition = definition_of_done(description=statement)
    references = (
        definition.references if definition.present else reference_line_headings(text=statement)
    )
    return pinned_sections(
        sections=sections, references=references, spec_tree=spec_tree, term_pattern=term_pattern
    )


def reserve_relevant_paragraphs(
    *, sections: Sequence[RelevantSection], terms: frozenset[str], remaining: int
) -> tuple[dict[tuple[str, int], tuple[tuple[int, str], ...]], int]:
    """Reserve matching deep paragraphs only when the complete tree cannot fit."""
    if remaining >= sum(len(section.full) - len(section.elided) for section in sections):
        return {}, remaining
    return select_by_relevance(sections=sections, terms=terms, remaining=remaining)


def combine_paragraphs(
    *,
    first: Mapping[tuple[str, int], Collection[tuple[int, str]]],
    second: Mapping[tuple[str, int], Collection[tuple[int, str]]],
) -> dict[tuple[str, int], tuple[tuple[int, str], ...]]:
    """Both paragraph reservations, ordered and deduplicated by source index."""
    return {
        key: tuple(sorted({index: text for index, text in entries}.items()))
        for key in first.keys() | second.keys()
        for entries in [(*first.get(key, ()), *second.get(key, ()))]
    }


def select_by_relevance(
    *, sections: Sequence[RelevantSection], terms: Collection[str], remaining: int
) -> tuple[dict[tuple[str, int], tuple[tuple[int, str], ...]], int]:
    """Reserve one share of ``remaining`` for matching paragraphs, in source order.

    A complete clause can be lexically relevant while still being too broad to
    spend the entire prompt on.  This pass runs before complete-clause selection
    so a smaller paragraph that states the behaviour remains available to the
    judgement.
    """
    budget = remaining // _SHARE
    selected: dict[tuple[str, int], list[tuple[int, str]]] = {}
    for section in sections:
        source = section.body if section.heading is not None else section.full
        for index, paragraph in enumerate(PARAGRAPH.findall(source)):
            if not _paragraph_matches(paragraph=paragraph, terms=terms):
                continue
            cost = len(paragraph)
            if section.key not in selected:
                cost += len(section.heading or "") + len(PARTIALLY_WITHHELD_BODY_MARKER)
                cost -= len(section.elided)
            if cost > budget:
                continue
            selected.setdefault(section.key, []).append((index, paragraph))
            budget -= cost
    return {key: tuple(paragraphs) for key, paragraphs in selected.items()}, remaining - (
        remaining // _SHARE - budget
    )


def _paragraph_matches(*, paragraph: str, terms: Collection[str]) -> bool:
    """Whether one paragraph shares a non-functional term with the behaviour."""
    paragraph_terms = frozenset(_TERM.findall(paragraph.casefold()))
    return bool(paragraph_terms & frozenset(terms))

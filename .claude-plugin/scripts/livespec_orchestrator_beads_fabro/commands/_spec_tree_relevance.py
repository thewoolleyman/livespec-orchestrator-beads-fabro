"""Length-normalised lexical ranking for condensed specification clauses."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from math import sqrt
from re import Pattern
from typing import Protocol, TypeVar

__all__: list[str] = ["relevance_order"]


class _RelevanceSection(Protocol):
    """The retrieval fields a condensed specification clause supplies."""

    @property
    def terms(self) -> frozenset[str]: ...

    @property
    def path(self) -> str: ...

    @property
    def index(self) -> int: ...


SectionT = TypeVar("SectionT", bound=_RelevanceSection)


def relevance_order(
    *, sections: Sequence[SectionT], statement: str, term_pattern: Pattern[str]
) -> list[SectionT]:
    """Rank sections by frequency-weighted relevance normalised by breadth."""
    wanted = frozenset(term_pattern.findall(statement.casefold()))
    frequency = Counter(term for section in sections for term in section.terms & wanted)
    decorated = [
        (
            (
                -sum(1.0 / (1 + frequency[term]) for term in sorted(section.terms & wanted))
                / sqrt(max(len(section.terms), 1)),
                section.path,
                section.index,
            ),
            section,
        )
        for section in sections
    ]
    decorated.sort(key=lambda pair: pair[0])
    return [section for _, section in decorated]

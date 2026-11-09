"""Paragraphs that name a literal command or marker the statement names.

A cited scenario need not carry a Governing clause line, and the paragraph that
states a slice's behaviour need not name the scenario, so neither the reference
line nor lexical overlap reaches a paragraph deep inside a large section. What
the statement and that paragraph do share is a backticked literal: the command
a slice adds and the marker line it writes. A literal in backticks is the
discriminator, because prose words are shared by far too many paragraphs.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    PARAGRAPH,
    PARTIALLY_WITHHELD_BODY_MARKER,
)

__all__: list[str] = ["identified_paragraphs", "merged_selection", "section_with_paragraphs"]

# The share of the remaining budget these paragraphs may spend, ahead of every
# other selection, so a slice's stating paragraph is kept whatever else the
# references and retrieval win.
_SHARE = 4

_SPAN = re.compile(r"`([^`\n]+)`")
_SEPARATORS = frozenset("-_./ ")
_MINIMUM_LENGTH = 8


class IdentifiedSection(Protocol):
    """The fields of one specification section this selection reads."""

    @property
    def key(self) -> tuple[str, int]: ...

    @property
    def heading(self) -> str | None: ...

    @property
    def body(self) -> str: ...

    @property
    def full(self) -> str: ...

    @property
    def elided(self) -> str: ...


def identified_paragraphs(
    *, sections: Sequence[IdentifiedSection], asked_text: str, remaining: int
) -> tuple[dict[tuple[str, int], tuple[tuple[int, str], ...]], int]:
    """Paragraphs naming the statement's literals, most-named first, and what budget is left."""
    identifiers = frozenset(
        span
        for span in _SPAN.findall(asked_text)
        if len(span) >= _MINIMUM_LENGTH and _SEPARATORS.intersection(span)
    )
    candidates = [
        (-named, order, index, section, paragraph)
        for order, section in enumerate(sections)
        for source in [section.body if section.heading is not None else section.full]
        if any(identifier in source for identifier in identifiers)
        for index, paragraph in enumerate(PARAGRAPH.findall(source))
        if (named := _named_count(paragraph=paragraph, identifiers=identifiers))
    ]
    candidates.sort(key=lambda candidate: candidate[:3])
    retained: dict[tuple[str, int], list[tuple[int, str]]] = {}
    budget = remaining // _SHARE
    spent = 0
    for _named, _order, index, section, paragraph in candidates:
        cost = len(paragraph)
        if section.key not in retained:
            cost += len(section.heading or "") + len(PARTIALLY_WITHHELD_BODY_MARKER)
            cost -= len(section.elided)
        if spent + cost <= budget:
            retained.setdefault(section.key, []).append((index, paragraph))
            spent += cost
    return {key: tuple(sorted(items)) for key, items in retained.items()}, remaining - spent


def merged_selection(
    *,
    sections: Sequence[IdentifiedSection],
    selected: Mapping[tuple[str, int], str],
    complete: Collection[tuple[str, int]],
    identified: Mapping[tuple[str, int], Collection[tuple[int, str]]],
) -> dict[tuple[str, int], str]:
    """`selected` with every retained paragraph added to a section not already whole."""
    by_key = {section.key: section for section in sections}
    return {
        **selected,
        **{
            key: section_with_paragraphs(
                section=by_key[key], current=selected.get(key), paragraphs=paragraphs
            )
            for key, paragraphs in identified.items()
            if key not in complete
        },
    }


def section_with_paragraphs(
    *,
    section: IdentifiedSection,
    current: str | None,
    paragraphs: Collection[tuple[int, str]],
) -> str:
    """`section` as `current` renders it, plus every retained paragraph it lacks."""
    prefix = section.heading or ""
    portion = (
        ""
        if current is None
        else current.removeprefix(prefix).removesuffix(PARTIALLY_WITHHELD_BODY_MARKER)
    )
    merged = portion + "".join(text for _index, text in paragraphs if text not in portion)
    if merged == (section.body if section.heading is not None else section.full):
        return section.full
    return f"{prefix}{merged}{PARTIALLY_WITHHELD_BODY_MARKER}"


def _named_count(*, paragraph: str, identifiers: Collection[str]) -> int:
    """How many of `identifiers` some backticked span of `paragraph` carries."""
    spans = _SPAN.findall(paragraph)
    return sum(any(identifier in span for span in spans) for identifier in identifiers)

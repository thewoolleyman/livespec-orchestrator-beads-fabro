"""Governing contracts explicitly named by scenario clauses."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from re import Pattern
from typing import Protocol, TypeVar

__all__: list[str] = ["governing_clause_references", "pinned_sections"]

_GOVERNING_CLAUSE = re.compile(
    "".join(
        [
            r'^Governing clause:\s+`(?P<path>[^`]+)`\s+§"(?P<heading>[^"]+)"',
            r'(?:\s+→\s+"(?P<paragraph>[^"]+)")?',
        ]
    ),
    re.MULTILINE,
)


class _PinnableSection(Protocol):
    """The fields of a specification section the reference pinning reads."""

    @property
    def path(self) -> str: ...

    @property
    def heading(self) -> str | None: ...

    @property
    def body(self) -> str: ...


SectionT = TypeVar("SectionT", bound=_PinnableSection)


def governing_clause_references(
    *, scenario_bodies: Collection[str], paths: Collection[str]
) -> tuple[tuple[str, str, str], ...]:
    """Resolve scenario pointers only when their cited spec file is present."""
    known_paths = frozenset(paths)
    return tuple(
        (match["path"], match["heading"], match["paragraph"] or "")
        for body in scenario_bodies
        for match in _GOVERNING_CLAUSE.finditer(body)
        if match["path"] in known_paths
    )


def pinned_sections(
    *,
    sections: Sequence[SectionT],
    references: Collection[str],
    spec_tree: Mapping[str, str],
    term_pattern: Pattern[str],
) -> tuple[list[SectionT], frozenset[str]]:
    """The sections a reference line cites, with those their scenarios' governing clauses cite."""
    pinned = [
        section
        for reference in references
        for section in sections
        if section.heading is not None and section.heading.rstrip(" \t") == reference.rstrip(" \t")
    ]
    governing = governing_clause_references(
        scenario_bodies=[section.body for section in pinned], paths=spec_tree
    )
    terms = frozenset(
        term
        for _path, _heading, paragraph in governing
        for term in term_pattern.findall(paragraph.casefold())
    )
    return (
        list(
            dict.fromkeys(
                [
                    *pinned,
                    *(
                        section
                        for path, heading, _paragraph in governing
                        for section in sections
                        if section.path == path
                        and section.heading is not None
                        and section.heading.rstrip(" \t") == f"## {heading}"
                    ),
                ]
            )
        ),
        terms,
    )

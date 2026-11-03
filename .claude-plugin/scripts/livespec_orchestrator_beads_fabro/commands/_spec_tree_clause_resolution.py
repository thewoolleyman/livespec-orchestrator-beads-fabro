"""Resolution of clauses and headings from a parsed specification tree."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Protocol, cast

__all__: list[str] = ["clauses_named", "headings_resolved"]


class _Clause(Protocol):
    """The provenance fields a named clause exposes."""

    @property
    def heading(self) -> str: ...

    @property
    def body(self) -> str: ...

    @property
    def path(self) -> str: ...


class _Section(Protocol):
    """The parsed section surface needed to resolve a named clause."""

    heading: str | None
    full: str

    def prompt_provenance_for(self, *, rendered: str) -> _Clause: ...


def clauses_named(
    *,
    spec_tree: Mapping[str, str],
    headings: Collection[str],
    sections_of: Callable[..., Sequence[object]],
) -> tuple[_Clause, ...]:
    """Resolve every named heading to full prompt provenance."""
    wanted = frozenset(headings)
    return tuple(
        section.prompt_provenance_for(rendered=section.full)
        for path in spec_tree
        for section in cast("Sequence[_Section]", sections_of(path=path, text=spec_tree[path]))
        if section.heading is not None and section.heading.rstrip(" \t") in wanted
    )


def headings_resolved(*, headings: Collection[str], clauses: Collection[_Clause]) -> bool:
    """Whether every named heading resolved to at least one supplied clause."""
    resolved = {clause.heading.rstrip(" \t") for clause in clauses}
    return all(heading in resolved for heading in headings)

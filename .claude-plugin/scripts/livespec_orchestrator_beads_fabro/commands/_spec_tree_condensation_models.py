"""Public value objects carried by spec-tree condensation consumers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, ValuesView
from dataclasses import dataclass, field

from typing_extensions import override

__all__: list[str] = [
    "CondensedClause",
    "CondensedSpecTree",
]


@dataclass(frozen=True, kw_only=True)
class CondensedClause:
    """One headed clause whose full body is provenance for a model prompt.

    `path` is the clause's file relative to the spec root. It rides OUTSIDE the
    equality the verdict-reuse comparison uses, because a clause moved between
    files is still the clause a verdict was judged against; the Definition-of-Done
    SPEC IDENTITY reads it, so the same move still changes that identity.
    """

    heading: str
    body: str
    path: str = field(default="", compare=False)


@dataclass(frozen=True, kw_only=True, eq=False)
class CondensedSpecTree:
    """The rendered tree and the full clauses selected into it."""

    tree: Mapping[str, str]
    clauses: tuple[CondensedClause, ...]

    def __getitem__(self, path: str) -> str:
        return self.tree[path]

    def __iter__(self) -> Iterator[str]:
        return iter(self.tree)

    def __len__(self) -> int:
        return len(self.tree)

    def values(self) -> ValuesView[str]:
        """The rendered file bodies, preserving the mapping-facing contract."""
        return self.tree.values()

    @override
    def __eq__(self, other: object) -> bool:
        return self.tree == other

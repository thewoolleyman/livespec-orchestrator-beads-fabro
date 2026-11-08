"""Governing contracts explicitly named by scenario clauses."""

from __future__ import annotations

import re
from collections.abc import Collection

__all__: list[str] = ["governing_clause_references"]

_GOVERNING_CLAUSE = re.compile(
    "".join(
        [
            r'^Governing clause:\s+`(?P<path>[^`]+)`\s+§"(?P<heading>[^"]+)"',
            r'(?:\s+→\s+"(?P<paragraph>[^"]+)")?',
        ]
    ),
    re.MULTILINE,
)


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

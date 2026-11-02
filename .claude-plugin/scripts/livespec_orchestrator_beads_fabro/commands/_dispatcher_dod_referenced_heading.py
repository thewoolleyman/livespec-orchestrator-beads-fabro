"""Render the bounded specification material for one Definition-of-Done reference."""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    CondensedClause,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = ["referenced_heading_body"]

_H2 = re.compile(r"^##\s+(.+?)\s*$")
_MARKER = re.compile(r"^##\s+")
_SPEC_DIRNAME = "SPECIFICATION"
_UNRESOLVED_HEADING_BODY = "(this heading does not resolve in the governed spec tree)"
_UNSELECTED_HEADING_BODY = (
    "(the governing-heading verdict named or selected no clause from this referenced heading)"
)


def referenced_heading_body(
    *,
    repo: Path,
    reference: str,
    governing: GoverningHeadingVerdict | None,
) -> str:
    """Render the governing verdict's verbatim clauses for one cited heading.

    The subject is bounded by the clauses the spec-stated judgement named or
    selected. Before that judgement is available, retain the whole section: an
    omitted body would turn an unobserved verdict into a claim that no clause
    governs. Once it is available, an explicit empty selection is the honest
    compact representation of a cited heading that did not contribute a clause.
    """
    if governing is None:
        return _heading_body(repo=repo, reference=reference)
    clauses = _governing_clauses_for(reference=reference, governing=governing)
    if not clauses:
        return _UNSELECTED_HEADING_BODY
    return "\n\n".join(f"{clause.heading}{clause.body}" for clause in clauses)


def _governing_clauses_for(
    *, reference: str, governing: GoverningHeadingVerdict
) -> tuple[CondensedClause, ...]:
    """Return unique selected and named clauses from one referenced H2.

    The two lists are distinct provenance roles, but a clause present in both
    appears once in the subject: duplicating identical text consumes the bound
    without giving the judge a second requirement to grade.
    """
    clauses: list[CondensedClause] = []
    for clause in (*governing.selected_clauses, *governing.named_clauses):
        if _title_of(heading=clause.heading) != _title_of(heading=reference) or clause in clauses:
            continue
        clauses.append(clause)
    return tuple(clauses)


def _title_of(*, heading: str) -> str:
    """Return a heading's title, whether or not it carries the optional `## ` marker."""
    return _MARKER.sub("", heading.strip()).strip()


def _heading_body(*, repo: Path, reference: str) -> str:
    """Return an H2 section body, retaining an explicit absence when unresolved."""
    title = _title_of(heading=reference)
    spec_root = repo / _SPEC_DIRNAME
    if not spec_root.is_dir():
        return _UNRESOLVED_HEADING_BODY
    for path in sorted(spec_root.glob("*.md")):
        read = attempt(action=lambda p=path: p.read_text(encoding="utf-8"), exceptions=(OSError,))
        if isinstance(read, AttemptFailure):
            continue
        body = _section_of(text=read, title=title)
        if body is not None:
            return body
    return _UNRESOLVED_HEADING_BODY


def _section_of(*, text: str, title: str) -> str | None:
    """Extract an H2 section through, but not including, the following H2."""
    collected: list[str] | None = None
    for raw in text.splitlines():
        match = _H2.match(raw)
        if match is None:
            if collected is not None:
                collected.append(raw)
            continue
        if collected is not None:
            break
        if match.group(1) == title:
            collected = [raw]
    return "\n".join(collected) if collected is not None else None

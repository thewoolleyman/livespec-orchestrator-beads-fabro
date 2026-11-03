"""Bounded rendering of the specification references in a judgement subject."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

__all__: list[str] = ["bounded_reference_blocks"]

_H2_MARKER = "## "
_SUBJECT_CHARACTER_LIMIT = 150_000
_UNSELECTED_HEADING_BODY = (
    "(the governing-heading verdict named or selected no clause from this referenced heading)"
)
_OVER_LIMIT_HEADING_BODY = (
    "(the referenced heading body was omitted because no governing-heading verdict "
    "named or selected no clause for it within this judgement's input bound)"
)


def bounded_reference_blocks(
    *,
    prefix: Sequence[str],
    references: Sequence[str],
    ending: Sequence[str],
    governing: GoverningHeadingVerdict | None,
    heading_body: Callable[[str], str],
) -> list[str]:
    """Render every verdict-named clause whole; bound only the no-verdict full bodies."""
    if governing is not None:
        return _reference_blocks(
            references=references,
            bodies=[
                _clause_body(reference=reference, governing=governing) for reference in references
            ],
        )
    bodies = [_OVER_LIMIT_HEADING_BODY for _ in references]
    for index, reference in enumerate(references):
        proposed = [*bodies]
        proposed[index] = heading_body(reference)
        if len(_render(prefix=prefix, references=references, bodies=proposed, ending=ending)) <= (
            _SUBJECT_CHARACTER_LIMIT
        ):
            bodies[index] = proposed[index]
    return _reference_blocks(references=references, bodies=bodies)


def _clause_body(*, reference: str, governing: GoverningHeadingVerdict) -> str:
    """Retain every named or selected clause for the cited heading, verbatim."""
    clauses = tuple(
        dict.fromkeys(
            clause
            for clause in (*governing.selected_clauses, *governing.named_clauses)
            if _heading_matches(reference=reference, heading=clause.heading)
        )
    )
    return "\n".join(clause.body for clause in clauses) if clauses else _UNSELECTED_HEADING_BODY


def _render(
    *,
    prefix: Sequence[str],
    references: Sequence[str],
    bodies: Sequence[str],
    ending: Sequence[str],
) -> str:
    """Measure the complete subject that one candidate reference set would produce."""
    return "\n".join([*prefix, *_reference_blocks(references=references, bodies=bodies), *ending])


def _reference_blocks(*, references: Sequence[str], bodies: Sequence[str]) -> list[str]:
    """Frame every reference body under the heading the rubric recognizes."""
    blocks: list[str] = []
    for reference, body in zip(references, bodies, strict=True):
        blocks.extend(("", f"## Referenced heading: {reference}", body))
    return blocks


def _heading_matches(*, reference: str, heading: str) -> bool:
    """Match a reference-line heading against recorded clause provenance."""
    return reference.removeprefix(_H2_MARKER).strip() == heading.removeprefix(_H2_MARKER).strip()

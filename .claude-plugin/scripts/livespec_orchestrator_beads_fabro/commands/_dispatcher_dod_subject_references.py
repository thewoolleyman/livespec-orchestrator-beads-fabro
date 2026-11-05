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
_OMITTED_CLAUSE_BODY = (
    "(a clause the governing-heading verdict named or selected was omitted because "
    "it does not fit within this judgement's input bound)"
)


def bounded_reference_blocks(
    *,
    prefix: Sequence[str],
    references: Sequence[str],
    ending: Sequence[str],
    governing: GoverningHeadingVerdict | None,
    heading_body: Callable[[str], str],
) -> list[str]:
    """Render each reference within the subject bound, keeping whatever clauses fit verbatim."""
    if governing is not None:
        return _bounded_clause_blocks(
            prefix=prefix, references=references, ending=ending, governing=governing
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


def _bounded_clause_blocks(
    *,
    prefix: Sequence[str],
    references: Sequence[str],
    ending: Sequence[str],
    governing: GoverningHeadingVerdict,
) -> list[str]:
    """Admit each named or selected clause verbatim while the whole subject still fits.

    Every clause starts omitted; a clause that does not fit is passed over rather
    than ending the walk, so one enormous clause cannot withhold smaller ones.
    """
    clauses = [_clauses_for(reference=reference, governing=governing) for reference in references]
    kept = [[False] * len(group) for group in clauses]

    def bodies() -> list[str]:
        return [
            _clause_body(clauses=group, kept=flags)
            for group, flags in zip(clauses, kept, strict=True)
        ]

    for group_index, group in enumerate(clauses):
        for clause_index in range(len(group)):
            kept[group_index][clause_index] = True
            if len(
                _render(prefix=prefix, references=references, bodies=bodies(), ending=ending)
            ) > (_SUBJECT_CHARACTER_LIMIT):
                kept[group_index][clause_index] = False
    return _reference_blocks(references=references, bodies=bodies())


def _clauses_for(*, reference: str, governing: GoverningHeadingVerdict) -> tuple[str, ...]:
    """Every named or selected clause body recorded for the cited heading, deduplicated."""
    return tuple(
        dict.fromkeys(
            clause.body
            for clause in (*governing.selected_clauses, *governing.named_clauses)
            if _heading_matches(reference=reference, heading=clause.heading)
        )
    )


def _clause_body(*, clauses: Sequence[str], kept: Sequence[bool]) -> str:
    """Join the kept clauses verbatim, with one marker per omitted clause."""
    if not clauses:
        return _UNSELECTED_HEADING_BODY
    return "\n".join(
        body if keep else _OMITTED_CLAUSE_BODY for body, keep in zip(clauses, kept, strict=True)
    )


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

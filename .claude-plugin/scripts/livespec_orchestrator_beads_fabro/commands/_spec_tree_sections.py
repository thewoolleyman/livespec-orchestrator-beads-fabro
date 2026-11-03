"""The H2-based section split shared by condensed specification-tree readers."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

__all__: list[str] = ["sections_of"]

SectionT = TypeVar("SectionT")

_H2_HEADING = re.compile(r"^##[ \t][^\n]*?[ \t]*$", re.MULTILINE)
_ELIDED_BODY_MARKER = (
    "(body omitted from this prompt: this clause was not selected as a candidate "
    "for this judgement, so its heading is listed but its text is not shown)"
)


def sections_of(*, path: str, text: str, make_section: Callable[..., SectionT]) -> list[SectionT]:
    """Split a file at its H2 headings, carrying its preamble first when present."""
    matches = list(_H2_HEADING.finditer(text))
    starts = [match.start() for match in matches]
    ends = [*starts[1:], len(text)] if starts else []
    preamble = text[: starts[0]] if starts else text
    sections = (
        [
            make_section(
                path=path,
                index=0,
                full=preamble,
                elided=f"{_ELIDED_BODY_MARKER}\n",
            )
        ]
        if preamble
        else []
    )
    for ordinal, (match, end) in enumerate(zip(matches, ends, strict=True)):
        sections.append(
            make_section(
                path=path,
                index=ordinal + 1,
                full=text[match.start() : end],
                elided=f"{match.group()}\n{_ELIDED_BODY_MARKER}\n",
                heading=match.group(),
                body=text[match.end() : end],
            )
        )
    return sections

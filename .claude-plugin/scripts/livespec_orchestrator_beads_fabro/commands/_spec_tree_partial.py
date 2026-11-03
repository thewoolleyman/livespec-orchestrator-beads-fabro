"""Partial rendering for a relevant spec section that exceeds its prompt budget."""

from __future__ import annotations

import re
from collections import Counter

__all__: list[str] = ["FUNCTION_TERMS", "partially_selected_section"]

# Words that carry no topic, so sharing one does not make a section relevant to a
# statement. They still weigh in the ranking, where inverse clause frequency already
# discounts them; only the decision to carry a section in part ignores them.
FUNCTION_TERMS = frozenset(
    "the and for are was with that this from not but its into onto when then than which".split()
)

_PARTIALLY_WITHHELD_BODY_MARKER = (
    "\n\n(body partially withheld from this prompt: the displayed leading text was selected "
    "for this judgement, but its remainder is not shown)\n"
)
_MINIMUM_BODY_CHARS = 2
_TERM = re.compile(r"[a-z0-9_]{3,}")
_PARAGRAPH = re.compile(r"(?:\A|\n{2,}).*?(?=\n{2,}|\Z)", re.DOTALL)


def partially_selected_section(
    *,
    heading: str | None,
    body: str,
    full: str,
    elided: str,
    remaining: int,
    terms: frozenset[str] | None = None,
) -> str | None:
    """Return marked leading text or relevant paragraphs within `remaining` budget."""
    prefix = heading or ""
    source = body if heading is not None else full
    marker_cost = len(prefix) + len(_PARTIALLY_WITHHELD_BODY_MARKER) - len(elided)
    body_budget = remaining - marker_cost
    if body_budget <= 0 or len(source) < _MINIMUM_BODY_CHARS:
        return None
    if terms is None:
        portion = source[: min(body_budget, len(source) - 1)]
        return f"{prefix}{portion}{_PARTIALLY_WITHHELD_BODY_MARKER}"
    paragraphs = [
        (index, paragraph, frozenset(_TERM.findall(paragraph.casefold())) & terms)
        for index, paragraph in enumerate(_PARAGRAPH.findall(source))
        if frozenset(_TERM.findall(paragraph.casefold())) & terms
    ]
    frequency = Counter(term for _, _, paragraph_terms in paragraphs for term in paragraph_terms)
    selected_parts: list[str] = []
    for _, paragraph, _paragraph_terms in sorted(
        paragraphs,
        key=lambda pair: (
            -sum(1 / frequency[term] for term in pair[2]),
            pair[0],
        ),
    ):
        if len(paragraph) <= body_budget:
            selected_parts.append(paragraph)
            body_budget -= len(paragraph)
    selected = "".join(selected_parts)
    if not selected:
        return None
    if selected == source:
        return full
    portion = selected
    return f"{prefix}{portion}{_PARTIALLY_WITHHELD_BODY_MARKER}"

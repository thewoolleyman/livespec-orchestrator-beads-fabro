"""Partial rendering for a relevant spec section that exceeds its prompt budget."""

from __future__ import annotations

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


def partially_selected_section(
    *,
    heading: str | None,
    body: str,
    full: str,
    elided: str,
    remaining: int,
) -> str | None:
    """Return leading body text and an in-band marker within `remaining` budget."""
    prefix = heading or ""
    source = body if heading is not None else full
    marker_cost = len(prefix) + len(_PARTIALLY_WITHHELD_BODY_MARKER) - len(elided)
    body_budget = remaining - marker_cost
    if body_budget <= 0 or len(source) < _MINIMUM_BODY_CHARS:
        return None
    portion = source[: min(body_budget, len(source) - 1)]
    return f"{prefix}{portion}{_PARTIALLY_WITHHELD_BODY_MARKER}"

"""How the condensation spends its budget, over the degenerate trees.

The paired ceiling test measures ONE judgement against this repository's real
spec tree, which is the assertion the work-item makes. It cannot reach the
shapes a real tree never has — an EMPTY tree, a file that opens on a heading
with no preamble before it, a budget so small that no clause body fits — and
each of those is a place a condensation can be wrong in a way no real-tree
measurement would show.

THE IDENTITY CASE IS THE CONTROL FOR ALL OF THEM. A tree that already fits must
come back UNCHANGED, byte for byte: a condensation that rewrote a tree it had
no need to touch would quietly change every judgement in every repository whose
spec tree is small, and the ceiling measurement — which only ever looks at a
tree far over the ceiling — could not tell.

THE ORDERING IS COUNTED IN CLAUSE BODIES WITHHELD, NOT IN CHARACTERS, and the
distinction is the elision's own doing: the marker that stands in for a body is
longer than a short body, so a tighter budget legitimately produces a LONGER
tree. Counting characters would therefore report the design working as the
design failing. What must be monotone is what the judge can read — the bodies —
and that is the property a future retrieval change is most likely to break
while still passing every fixed-size assertion.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    ELIDED_BODY_MARKER,
    PROMPT_CHARACTER_CEILING,
    condensed_spec_tree,
)

_PREAMBLE_FILE = "with-preamble.md"
_HEADLESS_FILE = "no-preamble.md"
_STATEMENT = "first clause"

_FIRST_BODY = "The first clause is what the statement is about. " * 8
_SECOND_BODY = "Unrelated prose about an entirely separate concern. " * 20
_ONLY_BODY = "More unrelated prose about a third concern. " * 40

_TREE = {
    _PREAMBLE_FILE: (
        "A preamble the file opens with, before any clause.\n\n"
        f"## First clause\n\n{_FIRST_BODY}\n\n"
        f"## Second clause\n\n{_SECOND_BODY}\n"
    ),
    _HEADLESS_FILE: f"## Only clause\n\n{_ONLY_BODY}\n",
}

# Measured against this fixture: the four budgets at which one more clause body
# fits than at the one before it, plus a budget under which none does.
_GRADED_CEILINGS = (0, 9900, 10300, 11500, 13000)


def _withheld(*, ceiling: int) -> int:
    """How many clause bodies the condensation withheld at one budget."""
    condensed = condensed_spec_tree(spec_tree=_TREE, statement=_STATEMENT, ceiling=ceiling)
    return sum(text.count(ELIDED_BODY_MARKER) for text in condensed.values())


def test_an_empty_tree_condenses_to_an_empty_tree() -> None:
    """A tree with no files is answered with one, not with a negative length.

    The rendered length of nothing is nothing, and the renderer joins blocks
    with a separator between them — so a length computed as `sum + separator *
    (blocks - 1)` is negative for an empty tree unless that case is answered
    first.
    """
    assert condensed_spec_tree(spec_tree={}, statement="anything") == {}


def test_a_tree_that_already_fits_comes_back_unchanged() -> None:
    """Under the ceiling the condensation is the identity, byte for byte."""
    assert condensed_spec_tree(spec_tree=_TREE, statement=_STATEMENT) == _TREE


def test_a_file_opening_on_a_heading_carries_no_invented_preamble() -> None:
    """A file whose first byte is a heading gains nothing before it."""
    condensed = condensed_spec_tree(spec_tree=_TREE, statement="only clause")

    assert condensed[_HEADLESS_FILE] == _TREE[_HEADLESS_FILE]


def test_a_budget_no_body_fits_under_still_answers_every_heading() -> None:
    """Every path and every heading survives a budget no clause body fits in.

    The paths are what the upstream renderer frames its blocks by and the
    headings are what a verdict may cite, so a tree that dropped either would
    hand the model a differently-shaped prompt rather than a smaller one.
    """
    condensed = condensed_spec_tree(spec_tree=_TREE, statement=_STATEMENT, ceiling=0)

    assert sorted(condensed) == sorted(_TREE)
    for heading in ("## First clause", "## Second clause"):
        assert heading in condensed[_PREAMBLE_FILE]
    assert "## Only clause" in condensed[_HEADLESS_FILE]
    for body in (_FIRST_BODY, _SECOND_BODY, _ONLY_BODY):
        assert body not in "".join(condensed.values())


def test_a_larger_budget_never_withholds_more_clause_bodies() -> None:
    """Raising the ceiling is monotone in the bodies the judge gets to read."""
    withheld = [_withheld(ceiling=ceiling) for ceiling in _GRADED_CEILINGS]

    assert withheld == sorted(withheld, reverse=True)
    assert withheld[0] == 4, "the tightest budget withholds every body in the fixture"
    assert withheld[-1] == 0, "the widest budget withholds none"
    assert len(set(withheld)) == len(withheld), (
        "the graded budgets no longer step one body at a time, so this fixture "
        "can no longer tell a monotone selection from a constant one"
    )
    assert _withheld(ceiling=PROMPT_CHARACTER_CEILING) == 0

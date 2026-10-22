"""How the condensation spends its budget, over the degenerate trees.

The paired ceiling test measures ONE judgement against this repository's real
spec tree, which is the assertion the work-item makes. It cannot reach the
shapes a real tree never has — an EMPTY tree, a file that opens on a heading
with no preamble before it, a budget so small that nothing fits — and each of
those is a place a condensation can be wrong in a way no real-tree measurement
would show.

THE IDENTITY CASE IS THE CONTROL FOR ALL OF THEM. A tree that already fits must
come back UNCHANGED, byte for byte: a condensation that rewrote a tree it had
no need to touch would quietly change every judgement in every repository whose
spec tree is small, and the ceiling measurement — which only ever looks at a
tree far over the ceiling — could not tell.

A SMALLER BUDGET NEVER CARRIES MORE TEXT, which is the ordering property the
greedy walk rests on and the one a future retrieval change is most likely to
break while still passing every fixed-size assertion.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    PROMPT_CHARACTER_CEILING,
    condensed_spec_tree,
)

_PREAMBLE_FILE = "with-preamble.md"
_HEADLESS_FILE = "no-preamble.md"

_TREE = {
    _PREAMBLE_FILE: (
        "A preamble the file opens with.\n\n"
        "## First clause\n\nThe first clause's body.\n\n"
        "## Second clause\n\nThe second clause's body.\n"
    ),
    _HEADLESS_FILE: "## Only clause\n\nThe only clause's body.\n",
}


def test_an_empty_tree_condenses_to_an_empty_tree() -> None:
    """A tree with no files is answered with one, not with a division by zero.

    The rendered length of nothing is nothing, and the renderer joins blocks
    with a separator between them — so a length computed as `sum + separator *
    (blocks - 1)` is negative for an empty tree unless that case is answered
    first.
    """
    assert condensed_spec_tree(spec_tree={}, statement="anything") == {}


def test_a_tree_that_already_fits_comes_back_unchanged() -> None:
    """Under the ceiling the condensation is the identity, byte for byte."""
    assert condensed_spec_tree(spec_tree=_TREE, statement="first clause") == _TREE


def test_a_file_opening_on_a_heading_carries_no_invented_preamble() -> None:
    """A file whose first byte is a heading gains nothing before it."""
    condensed = condensed_spec_tree(spec_tree=_TREE, statement="only clause")

    assert condensed[_HEADLESS_FILE] == _TREE[_HEADLESS_FILE]


def test_a_budget_nothing_fits_under_still_answers_every_path() -> None:
    """Every path survives a budget no clause fits in, carrying no clause text.

    The paths are what the upstream renderer frames its blocks by, so a tree
    that dropped a path would hand the model a differently-shaped prompt rather
    than a smaller one.
    """
    condensed = condensed_spec_tree(spec_tree=_TREE, statement="first clause", ceiling=0)

    assert sorted(condensed) == sorted(_TREE)
    assert set(condensed.values()) == {""}


def test_a_smaller_budget_never_carries_more_text() -> None:
    """Shrinking the ceiling is monotone in the characters the tree carries."""
    carried = [
        sum(
            len(text)
            for text in condensed_spec_tree(
                spec_tree=_TREE, statement="first clause", ceiling=ceiling
            ).values()
        )
        for ceiling in (0, 1100, 1140, PROMPT_CHARACTER_CEILING)
    ]

    assert carried == sorted(carried)
    assert carried[0] == 0
    assert carried[-1] == sum(len(text) for text in _TREE.values())

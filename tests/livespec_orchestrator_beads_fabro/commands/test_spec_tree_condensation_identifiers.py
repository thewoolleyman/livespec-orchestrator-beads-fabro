"""A paragraph naming a literal command or marker the statement names is retained.

The shape is the one a real slice carried: the referenced scenario has no
Governing clause line, the stating paragraph sits at the end of a large section
whose body the ceiling would otherwise withhold, and no sentence links the two.
The only link is the backticked command and marker both texts name.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    PROMPT_CHARACTER_CEILING,
    condensed_spec_tree,
)

_SCENARIO_HEADING = "## Scenario 185 — A released item's recovery route is decided before admission"
_CONTRACT_HEADING = "## Factory-configurable ACP fallback priority"
_STATING_PARAGRAPH = (
    "**A ruled seed names the tree a released item's next dispatch starts from.** "
    "An operator MAY run `dispatcher.py seed-ruling --repo <path> --item <id>`. "
    "The comment MUST open with the marker line `livespec-seed-ruling`. "
    "The comment MUST pass the shared template-opener detector before it is written."
)
_DECOY_PARAGRAPH = (
    "**A fresh ruling routes a released item's next dispatch fresh.** "
    "An operator MAY run `dispatcher.py fresh-ruling --repo <path> --item <id>`. "
    "The comment MUST open with the marker line `livespec-fresh-ruling`."
)
_FILLER = "unrelated policy background.\n\n" * 15_000


def _tree() -> dict[str, str]:
    return {
        "contracts.md": (
            f"# Contracts\n\n{_CONTRACT_HEADING}\n\n{_FILLER}"
            f"{_DECOY_PARAGRAPH}\n\n{_FILLER}{_STATING_PARAGRAPH}\n"
        ),
        "scenarios.md": (
            f"{_SCENARIO_HEADING}\n\n"
            "Scenario: an unanchorable released item is seeded from verified preserved work.\n"
        ),
    }


def _statement(*, bullet: str) -> str:
    return (
        "## Definition of Done\n\n"
        f"References: {_SCENARIO_HEADING}\n\n"
        f"- {bullet}\n"
        "- The comment is refused when it opens with a template opener.\n"
    )


def test_a_paragraph_naming_the_statements_command_and_marker_is_kept_in_full() -> None:
    """The stating paragraph reaches the judgement though no heading links it."""
    statement = _statement(
        bullet=(
            "A `dispatcher.py seed-ruling` command writes a comment opening with the "
            "marker line `livespec-seed-ruling`."
        )
    )

    condensed = condensed_spec_tree(
        spec_tree=_tree(), statement=statement, ceiling=PROMPT_CHARACTER_CEILING
    )

    assert _STATING_PARAGRAPH in condensed["contracts.md"]


def test_a_statement_naming_neither_identifier_keeps_the_relevant_paragraph() -> None:
    """Lexical relevance reaches a deep stating paragraph without a literal identifier."""
    statement = _statement(bullet="A command writes a comment recording a ruled seed.")

    condensed = condensed_spec_tree(
        spec_tree=_tree(), statement=statement, ceiling=PROMPT_CHARACTER_CEILING
    )

    assert _STATING_PARAGRAPH in condensed["contracts.md"]

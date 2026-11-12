"""The paragraph reservation that precedes broad clause selection."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    _partial_selection,
    _section,
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_relevant_paragraphs import (
    select_by_relevance,
)
from returns.pipeline import is_successful


@dataclass(frozen=True, kw_only=True)
class _Section:
    key: tuple[str, int]
    heading: str | None
    body: str
    full: str
    elided: str


def test_select_by_relevance_skips_a_broad_paragraph_for_a_later_stating_one() -> None:
    """A paragraph larger than the reservation cannot displace a fitting statement."""
    broad = "credential helper " * 100
    stating = "A credential helper is private to repository hooks."
    selected, remaining = select_by_relevance(
        sections=(
            _relevant_section(key=("first", 0), body=f"Preamble.\n\n{broad}"),
            _relevant_section(key=("second", 0), body=f"Preamble.\n\n{stating}"),
        ),
        terms={"credential", "helper"},
        remaining=1_000,
    )

    assert selected == {("second", 0): ((1, "\n\n" + stating),)}
    assert remaining < 1_000


def test_select_by_relevance_keeps_each_fitting_matching_paragraph() -> None:
    """A section pays its framing cost once when it contributes several paragraphs."""
    first = "Credential helpers are private."
    second = "Hooks use credential helpers."
    third = "Credential helpers protect hooks."
    selected, _ = select_by_relevance(
        sections=(_relevant_section(key=("contracts", 0), body=f"{first}\n\n{second}\n\n{third}"),),
        terms={"credential", "helpers"},
        remaining=1_000,
    )

    assert selected == {("contracts", 0): ((1, "\n\n" + second), (2, "\n\n" + third))}


def test_select_by_relevance_ignores_paragraphs_without_a_matching_term() -> None:
    """The reservation is unspent when the statement has no lexical candidate."""
    selected, remaining = select_by_relevance(
        sections=(_relevant_section(key=("contracts", 0), body="Preamble.\n\nUnrelated text."),),
        terms={"credential"},
        remaining=1_000,
    )

    assert selected == {}
    assert remaining == 1_000


def test_condensation_skips_an_unmatched_unpinned_partial_clause() -> None:
    """No lexical match means an unpinned section has no partial selection."""
    section = _section(
        path="contracts.md",
        index=0,
        full="## Unrelated\n\nUnrelated prose.",
        elided="## Unrelated\n\n(body omitted)",
        heading="## Unrelated",
        body="\n\nUnrelated prose.",
    )

    assert (
        _partial_selection(
            section=section, pinned=False, matching_terms=frozenset(), remaining=1_000
        )
        is None
    )


def test_judge_within_ceiling_uses_the_shared_judgement_with_a_condensed_tree() -> None:
    """The public judge wrapper retains its model seam after condensation."""
    result = judge_within_ceiling(
        spec_tree={"contracts.md": "## Clause\n\nCredential helpers remain private.\n"},
        statement="Credential helpers remain private.",
        run_model=lambda _prompt: (
            '{"kind":"stated","stated_by":["## Clause"],'
            '"generalization_target":null,"rationale":""}'
        ),
    )

    assert is_successful(result)


def _relevant_section(*, key: tuple[str, int], body: str) -> _Section:
    """A headed section whose marker-only form is smaller than its body."""
    heading = "## Clause"
    return _Section(
        key=key,
        heading=heading,
        body=body,
        full=f"{heading}\n\n{body}",
        elided=f"{heading}\n\n(body omitted)",
    )

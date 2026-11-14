"""Edge coverage for governing-heading evidence validation."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    _evidence_matches_named_clauses,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause
from livespec_runtime.spec_stated import ClauseEvidence

_HEADING = "## Governing heading"
_CLAUSE = CondensedClause(
    heading=_HEADING,
    body="The controls retain the recorded governing verdict.",
)
_STATEMENT = "The controls retain the recorded governing verdict."


def test_evidence_rejects_more_than_one_quote_for_a_named_heading() -> None:
    assert (
        _evidence_matches_named_clauses(
            stated_by=(_HEADING,),
            evidence=(
                ClauseEvidence(
                    heading=_HEADING, quote="The controls retain the recorded governing verdict."
                ),
                ClauseEvidence(
                    heading=_HEADING, quote="The controls retain the recorded governing verdict."
                ),
            ),
            named=(_CLAUSE,),
            statement=_STATEMENT,
        )
        is False
    )


def test_evidence_rejects_a_clause_quote_without_statement_terms() -> None:
    clause = CondensedClause(heading=_HEADING, body="The and this.")
    assert (
        _evidence_matches_named_clauses(
            stated_by=(_HEADING,),
            evidence=(ClauseEvidence(heading=_HEADING, quote="The and this."),),
            named=(clause,),
            statement=_STATEMENT,
        )
        is False
    )

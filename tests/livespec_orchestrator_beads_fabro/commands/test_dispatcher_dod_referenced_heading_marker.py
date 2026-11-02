"""A referenced heading keeps its governing clauses whether or not it carries the `## ` marker."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_referenced_heading import (
    referenced_heading_body,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    CondensedClause,
)

_CLAUSE = CondensedClause(
    heading="## Target",
    body="\nThe selected clause remains verbatim.\n",
    path="contracts.md",
)
_VERDICT = GoverningHeadingVerdict(
    kind="stated",
    stated_by=("## Target",),
    selected_clauses=(_CLAUSE,),
    named_clauses=(),
)


@pytest.mark.parametrize(
    "reference",
    ["## Target", "Target", "##   Target  ", "  Target\t"],
)
def test_a_reference_spelled_with_or_without_the_marker_keeps_its_selected_clause(
    reference: str,
) -> None:
    body = referenced_heading_body(repo=Path(), reference=reference, governing=_VERDICT)

    assert _CLAUSE.body in body


def test_a_reference_naming_another_heading_still_renders_the_unselected_placeholder() -> None:
    body = referenced_heading_body(repo=Path(), reference="Other", governing=_VERDICT)

    assert _CLAUSE.body not in body
    assert "named or selected no clause" in body


def test_a_clause_named_and_selected_appears_once_under_a_bare_reference() -> None:
    verdict = replace(_VERDICT, named_clauses=(_CLAUSE,))

    body = referenced_heading_body(repo=Path(), reference="Target", governing=verdict)

    assert body.count(_CLAUSE.body) == 1

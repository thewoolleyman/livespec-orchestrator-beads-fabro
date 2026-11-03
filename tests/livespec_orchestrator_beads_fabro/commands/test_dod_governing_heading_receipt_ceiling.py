"""The governing-heading receipt records the clause set the model was shown.

The judgement condenses the spec tree at the prompt ceiling MINUS the correction
prompt's headroom, so the receipt must condense at that same reduced ceiling. A
clause that fits only at the full ceiling is absent from the prompt, and a
receipt recording it would let a later reuse read claim the model saw text it
never did.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    governing_heading_statement,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import (
    correction_prompt_headroom,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    PROMPT_CHARACTER_CEILING,
    condensed_spec_tree,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_REPLY = (
    '{"kind": "stated", "stated_by": ["' + _GOVERNING + '"],'
    ' "generalization_target": null, "rationale": "The scenario states it.",'
    ' "evidence": [{"heading": "'
    + _GOVERNING
    + '", "quote": "The checks consult the judgement."}]}'
)


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-m76p2n",
        type="feature",
        status="ready",
        title="The citation checks consult the spec-stated judgement",
        description=f"## Definition of Done\n\n- The checks consult the judgement.\n\nReferences: {_CITED}\n",
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _tree(*, repo: Path, padding: int) -> dict[str, str]:
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nThe checks consult the judgement.\n\n"
        f"{_CITED}\n\n{'x' * padding}\n",
        encoding="utf-8",
    )
    return dict(read_current_specification(spec_root=spec).files)


def _carries_cited(*, tree: dict[str, str], statement: str, ceiling: int) -> bool:
    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=ceiling)
    return any(clause.heading.rstrip(" \t") == _CITED for clause in condensed.clauses)


def test_the_receipt_records_the_clause_set_the_headroom_reduced_prompt_carried(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    item = _item()
    statement = governing_heading_statement(
        item=item, section=definition_of_done(description=item.description)
    )
    low, high = 0, PROMPT_CHARACTER_CEILING
    while high - low > 1:
        middle = (low + high) // 2
        tree = _tree(repo=repo, padding=middle)
        if _carries_cited(tree=tree, statement=statement, ceiling=PROMPT_CHARACTER_CEILING):
            low = middle
        else:
            high = middle
    tree = _tree(repo=repo, padding=low)
    reduced = PROMPT_CHARACTER_CEILING - correction_prompt_headroom(spec_tree=tree)
    assert _carries_cited(tree=tree, statement=statement, ceiling=PROMPT_CHARACTER_CEILING)
    assert not _carries_cited(tree=tree, statement=statement, ceiling=reduced)

    verdict = governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: _REPLY)

    assert verdict is not None
    assert _CITED not in {clause.heading.rstrip(" \t") for clause in verdict.selected_clauses}

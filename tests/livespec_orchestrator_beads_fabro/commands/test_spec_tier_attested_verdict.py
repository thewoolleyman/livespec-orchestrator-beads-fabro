"""A standing attestation supplies the governing-heading verdict every taking uses.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` requires "every taking,
the pre-dispatch wall and the `dod_gate` node included" to "use the attested
`stated` verdict without requiring model agreement", with "its clause provenance"
being "the cited clause, as both the selected and the named clause". The
Definition-of-Done judgement reads it through its governing-heading reuse read and
the `dod_gate` node reads it off the goal block, so both are driven here.

THE ABSENT-ATTESTATION CASE NAMES A REPOSITORY THAT DOES NOT EXIST, because the
ledger is checked before the disk: an item nobody attested must not cost a
specification read on every taking and every goal render.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GOVERNING_HEADING_BLOCK_HEADING,
)
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import attestation_comment
from livespec_orchestrator_beads_fabro.commands._spec_tier_attested_verdict import (
    attested_governing_heading,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Clause A"
_TEXT = f"# Contracts\n\n{_HEADING}\n\nBody A.\n"


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-attested",
        type="feature",
        status="ready",
        title="An attested feature",
        description=f"## Definition of Done\n\n- It does the thing.\n\nReferences: {_HEADING}\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path, text: str = _TEXT) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(text, encoding="utf-8")
    return repo


def _attestation() -> str:
    clause = clauses_named(spec_tree={"contracts.md": _TEXT}, headings=[_HEADING])[0]
    return attestation_comment(item=_item(), actor="human:chad", clause=clause, spec_version="3")


def test_an_item_nobody_attested_costs_no_specification_read(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-repository"

    assert attested_governing_heading(item=_item(), repo=missing, comments=("a rider",)) is None


def test_a_standing_attestation_is_a_stated_verdict_with_the_cited_clause_as_provenance(
    tmp_path: Path,
) -> None:
    verdict = attested_governing_heading(
        item=_item(), repo=_repo(tmp_path=tmp_path), comments=(_attestation(),)
    )

    assert verdict is not None
    assert verdict.kind == "stated"
    assert verdict.stated_by == (_HEADING,)
    assert verdict.generalization_target is None
    assert verdict.provenance_complete is True
    assert [clause.heading for clause in verdict.selected_clauses] == [_HEADING]
    assert verdict.selected_clauses == verdict.named_clauses


def test_a_rewritten_cited_clause_supplies_no_verdict(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, text=_TEXT.replace("Body A.", "Body A, rewritten."))

    assert attested_governing_heading(item=_item(), repo=repo, comments=(_attestation(),)) is None


def test_an_unreadable_specification_tree_supplies_no_verdict(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = (repo / "SPECIFICATION" / "contracts.md").write_bytes(b"\xff\xfe not utf-8")

    assert attested_governing_heading(item=_item(), repo=repo, comments=(_attestation(),)) is None


def test_the_definition_of_done_reuse_read_returns_the_attested_verdict(tmp_path: Path) -> None:
    verdict = reusable_governing_heading_verdict(
        item=_item(), repo=_repo(tmp_path=tmp_path), comments=(_attestation(),)
    )

    assert verdict is not None
    assert verdict.kind == "stated"
    assert verdict.stated_by == (_HEADING,)


def test_the_goal_block_the_dod_gate_node_reads_carries_the_attested_verdict(
    tmp_path: Path,
) -> None:
    comments = (
        WorkItemComment(text=_attestation(), author="human", created_at="2026-10-28T00:00:00Z"),
    )

    goal = render_goal(
        item=_item(), repo=_repo(tmp_path=tmp_path), branch="feat/x", comments=comments
    )

    block = goal[goal.index(GOVERNING_HEADING_BLOCK_HEADING) :]
    assert "kind: stated" in block
    assert f"governing heading: {_HEADING}" in block

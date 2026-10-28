"""The SPEC IDENTITY a host taking used is recorded, journaled and supplied to the run.

`test_dod_clause_spec_identity.py` covers what the identity IS and when a taking
reuses a record on it. This module covers where the identity goes afterwards: the
judgement record that carries it, the dispatch-journal row, the goal block that
supplies it to the run, and the digest the `dod_gate` node then compares on.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_judgement_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
    judgement_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    GoverningHeadingReceipt,
    reusable_governing_heading,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SPEC_IDENTITY_BLOCK_HEADING,
    SPEC_IDENTITY_JOURNAL_STAGE,
    SpecIdentity,
    spec_identity_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity_record import (
    node_subject_digest,
    recorded_spec_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 240 — A recorded verdict binds identical digests"
_IDENTITY = SpecIdentity(
    form="clauses",
    value="clauses:abc123",
    selected=(CondensedClause(heading=_HEADING, body="\nBody.\n", path="scenarios.md"),),
    named=(CondensedClause(heading="## Other", body="\nOther.\n", path="contracts.md"),),
)


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-onrjh3",
        type="feature",
        status="ready",
        title="Reuse a host verdict across an unrelated revision",
        description=(
            "## Definition of Done\n\n- A recorded verdict binds identical digests.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-27T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    return repo


def _record(*, identity: SpecIdentity | None) -> str:
    return verdict_comment(
        item_id="bd-ib-onrjh3",
        stage=STAGE_PRE_DISPATCH,
        digest="d",
        rubric_digest="r",
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        spec_identity=identity,
    )


def test_a_record_carries_the_spec_identity_it_was_taken_under() -> None:
    body = _record(identity=_IDENTITY)

    recorded = recorded_spec_identity(comments=("a rider", body, "a later rider"))

    assert recorded is not None
    assert (recorded.form, recorded.value) == ("clauses", "clauses:abc123")
    assert recorded_spec_identity(comments=()) is None
    assert recorded_spec_identity(comments=("only a rider",)) is None


def test_the_newest_record_governs_and_one_naming_no_identity_supplies_none() -> None:
    older = _record(identity=_IDENTITY)
    newer = _record(identity=replace(_IDENTITY, form="tree", value="tree:def456"))
    legacy = _record(identity=None)

    assert recorded_spec_identity(comments=(older, newer)) == SpecIdentity(
        form="tree", value="tree:def456"
    )
    assert recorded_spec_identity(comments=(older, legacy)) is None


def test_the_goal_supplies_the_recorded_identity_and_names_nothing_when_there_is_none(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    supplied = (WorkItemComment(text=_record(identity=_IDENTITY), author=None, created_at=None),)

    with_identity = render_goal(item=_item(), repo=repo, branch="feat/x", comments=supplied)
    without = render_goal(item=_item(), repo=repo, branch="feat/x")

    assert SPEC_IDENTITY_BLOCK_HEADING in with_identity
    assert "identity: clauses:abc123" in with_identity
    assert "form: clauses" in with_identity
    assert SPEC_IDENTITY_BLOCK_HEADING not in without


def test_the_node_digest_comes_from_the_supplied_identity_else_the_whole_tree(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    supplied = (_record(identity=_IDENTITY),)

    assert node_subject_digest(item=item, cwd=repo, comments=supplied) == judgement_subject_digest(
        item=item, cwd=repo, comments=supplied, spec_identity="clauses:abc123"
    )
    unsupplied = judgement_subject_digest(item=item, cwd=repo)
    assert node_subject_digest(item=item, cwd=repo, comments=()) == unsupplied
    assert node_subject_digest(item=item, cwd=repo, comments=supplied) != unsupplied


def test_the_journal_row_names_the_form_the_value_and_each_clause_by_address() -> None:
    row = spec_identity_journal_record(
        work_item_id="bd-ib-onrjh3", stage=STAGE_PRE_DISPATCH, identity=_IDENTITY
    )

    assert row["stage"] == SPEC_IDENTITY_JOURNAL_STAGE
    assert row["work_item_id"] == "bd-ib-onrjh3"
    assert row["judgement_stage"] == STAGE_PRE_DISPATCH
    assert row["spec_identity_form"] == "clauses"
    assert row["spec_identity"] == "clauses:abc123"
    provenance = row["clause_provenance"]
    assert isinstance(provenance, list)
    assert [(one["list"], one["path"], one["heading"]) for one in provenance] == [
        ("selected", "scenarios.md", _HEADING),
        ("named", "contracts.md", "## Other"),
    ]
    assert all(len(one["body_sha256"]) == 64 for one in provenance)


class _Journal:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.rows.append(record)


@pytest.mark.parametrize("journaled", [True, False])
def test_the_wall_journals_the_identity_of_every_taking_that_produced_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, journaled: bool
) -> None:
    repo = _repo(tmp_path=tmp_path)
    decision = DodJudgementDecision(
        work_item_id="bd-ib-onrjh3",
        outcome=JUDGEMENT_ADMITTED,
        reused=True,
        spec_identity=_IDENTITY if journaled else None,
    )
    monkeypatch.setattr(wall, "judge_item_definition_of_done", lambda **_kwargs: decision)
    journal = _Journal()

    refusal = wall.dod_judgement_refusal(repo=repo, items=[_item()], journal=journal)
    absent = wall.dod_judgement_refusal(repo=repo, items=[_item()])

    assert refusal is None
    assert absent is None
    assert [row["stage"] for row in journal.rows] == (
        [SPEC_IDENTITY_JOURNAL_STAGE] if journaled else []
    )


def test_a_clause_moved_between_files_is_still_the_clause_a_verdict_was_judged_against() -> None:
    old = CondensedClause(heading=_HEADING, body="\nBody.\n", path="old.md")
    moved = CondensedClause(heading=_HEADING, body="\nBody.\n", path="new.md")

    assert old == moved

    verdict = GoverningHeadingVerdict(
        kind="stated", stated_by=(_HEADING,), selected_clauses=(old,), named_clauses=(old,)
    )
    body = verdict_comment(
        item_id="bd-ib-onrjh3",
        stage=STAGE_PRE_DISPATCH,
        digest="d",
        rubric_digest="r",
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(verdict=verdict, subject_digest="s"),
    )

    reused = reusable_governing_heading(
        comments=(body,), subject_digest="s", selected_clauses=(moved,), named_clauses=(moved,)
    )

    assert reused is not None
    assert [clause.path for clause in reused.selected_clauses] == ["new.md"]
    assert [clause.path for clause in reused.named_clauses] == ["new.md"]

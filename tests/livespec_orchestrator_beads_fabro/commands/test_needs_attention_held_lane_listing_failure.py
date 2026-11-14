"""The held-Definition-of-Done lane when the tenant listing cannot be read.

The lane finds the items a judgement was recorded against from one tenant
listing. A listing that fails is the absence of evidence that a verdict stands,
and `needs-attention` composes many lanes over the whole tenant, so the lane
reports nothing rather than raising out of the snapshot.

THE CONTROL IS THE SAME ITEM, RECORDED VERDICT AND MARKER read through a tenant
whose listing works: without it the empty answer is equally consistent with a
lane that reports nothing for any item.

A marked item whose recorded verdict no longer matches the item's current
judgement digest is not held, so the marker narrows which comments are read
without deciding that an item is held.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_dod_judgement_marker
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dod_judgement_marker import (
    mark_work_item_dod_judgement_recorded,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    DodJudgement,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._needs_attention_definition_of_done"
_HEADING = "## Scenario 999 — The dispatcher refuses an unresolvable workflow variant"


class _RefusingListing:
    def list_issues(self) -> list[dict[str, object]]:
        raise BeadsCommandError(command="bd list", exit_code=1, stderr="listing refused")


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="bd-ib-held",
            type="task",
            status="ready",
            title="A held item",
            description=(
                "## Definition of Done\n\n- The dispatcher refuses an unresolvable workflow"
                f" variant.\n\nReferences: {_HEADING}\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-04T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
        )
    )


def _held_fixture(*, tmp_path: Path) -> tuple[Path, WorkItem]:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )
    item = _item()
    append_work_item(path=config, item=item)
    rubric = judgement_rubric()
    assert rubric is not None
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=verdict_comment(
            item_id=item.id,
            stage=STAGE_PRE_DISPATCH,
            digest=judgement_subject_digest(item=item, cwd=repo),
            rubric_digest=rubric_digest(rubric=rubric),
            judgement=DodJudgement(outcome=JUDGEMENT_HELD, findings=("bd-ib-held: fix it.",)),
        ),
    )
    mark_work_item_dod_judgement_recorded(path=config, item_id=item.id)
    return repo, item


def test_an_unreadable_listing_reports_nothing_while_a_readable_one_reports_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    module = importlib.import_module(_MODULE)
    repo, item = _held_fixture(tmp_path=tmp_path)

    readable = module.held_definition_of_done_items(project_root=repo, repo="repo", items=[item])

    monkeypatch.setattr(
        _store_dod_judgement_marker, "make_beads_client", lambda **_: _RefusingListing()
    )
    unreadable = module.held_definition_of_done_items(project_root=repo, repo="repo", items=[item])
    reset_fake_singleton()

    assert [str(fact.id) for fact in readable] == ["hygiene:held-definition-of-done:bd-ib-held"]
    assert unreadable == []


def test_a_marked_item_whose_recorded_verdict_is_stale_is_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    module = importlib.import_module(_MODULE)
    repo, item = _held_fixture(tmp_path=tmp_path)
    edited = replace(item, description=f"{item.description}\n- Another assertion.\n")

    held = module.held_definition_of_done_items(project_root=repo, repo="repo", items=[edited])
    reset_fake_singleton()

    assert held == []

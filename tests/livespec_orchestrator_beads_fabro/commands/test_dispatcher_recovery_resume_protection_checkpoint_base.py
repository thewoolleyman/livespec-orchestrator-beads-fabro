"""A checkpoint-failed seed's base never stands in for its preserved ref tip."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import ResumeObservation
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEAD = "a" * 40


def _item() -> WorkItem:
    return WorkItem(
        id="item",
        type="bug",
        status="ready",
        title="checkpoint base",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _gather() -> ResumeGather:
    return ResumeGather(
        observation=ResumeObservation(
            work_item_id="item",
            status="ready",
            pull_request=1,
            pull_request_head=_HEAD,
            liveness_observed=True,
        ),
        anchor=ResumeAnchor(
            record=Mock(), run_id="run-1", head=_HEAD, resumed_at="pr", source="factory"
        ),
        branch="feat/item",
        earlier_run_ids=("run-1",),
        workflow_name=None,
        publications=((_HEAD, "run-1"),),
    )


@pytest.mark.parametrize(("tip", "kind"), [("c" * 40, "different"), (_HEAD, "same")])
def test_the_published_head_is_compared_against_the_preserved_ref_tip_not_the_seed_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tip: str, kind: str
) -> None:
    """A tip that differs from the head is measured even when the seed base equals the head."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_resume_protection"
    )
    descendant = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("", encoding="utf-8")
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha=_HEAD,
        preservation_ref="refs/livespec/preserved-publish/item/c",
        preservation_tip_sha=tip,
    )
    comparison = Mock(
        return_value=descendant.PreservedDescendant(
            preservation_ref=seed.preservation_ref,
            preservation_tip=tip,
            published_head=_HEAD,
        )
    )
    monkeypatch.setattr(module, "read_journal_records", Mock(return_value=()))
    monkeypatch.setattr(module, "verified_preserved_seed", Mock(return_value=seed))
    monkeypatch.setattr(module, "published_head_relation", Mock(return_value=False))
    monkeypatch.setattr(module, "preserved_descendant", comparison)

    result = module.protected_resume_seed(
        gather=_gather(), item=_item(), repo=tmp_path, runner=Mock(), journal=journal
    )

    assert comparison.called is (kind == "different")
    assert (result == seed) is (kind == "different")

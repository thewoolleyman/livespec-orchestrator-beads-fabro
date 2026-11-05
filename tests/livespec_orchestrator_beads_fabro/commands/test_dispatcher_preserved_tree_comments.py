"""The durable comment projection used when recovery has no local journal row."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_terminal_preservation as preservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_comments import (
    preserved_tree_comment_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import ROUTE_HELD
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import ResumeObservation
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-vraou4"
_RUN = "01M6JSNVH32S8CDNX0P4TS7DWB"
_BASE = "a" * 40
_COMMIT = "b" * 40
_REF = f"refs/livespec/preserved-publish/{_ITEM}/{_COMMIT}"


def _comment(*, text: str) -> WorkItemComment:
    return WorkItemComment(text=text, author="dispatcher", created_at="2026-11-05T00:00:00Z")


def _preserved_comment(*, item: str = _ITEM) -> WorkItemComment:
    return _comment(
        text="\n".join(
            (
                "livespec-preserved-tree",
                "",
                f"work-item: {item}",
                f"run id: {_RUN}",
                "factory: petri",
                f"preservation ref: {_REF}",
                f"commit id: {_COMMIT}",
                f"base commit: {_BASE}",
            )
        )
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="Preserve the cancelled run",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_the_newest_complete_comment_names_a_seed_and_ignores_noise() -> None:
    """Only a complete marker for this item can become a later dispatch's seed."""
    seed = preserved_tree_comment_seed(
        comments=(
            _comment(text="operator rider"),
            _preserved_comment(),
            _comment(text=f"livespec-preserved-tree\nwork-item: {_ITEM}"),
            _preserved_comment(item="bd-ib-someone-else"),
        ),
        work_item_id=_ITEM,
    )

    assert seed is not None
    assert seed.source_run_id == _RUN
    assert seed.remote == "origin"
    assert seed.commit_sha == _BASE
    assert seed.preservation_ref == _REF


def test_an_incomplete_or_unmarked_comment_never_invents_a_seed() -> None:
    assert (
        preserved_tree_comment_seed(comments=(_comment(text="ordinary rider"),), work_item_id=_ITEM)
        is None
    )


def test_an_unreadable_comment_sidecar_holds_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed durable-comment read cannot be treated as confirmed absence."""
    monkeypatch.setattr(routing, "read_dispatch_comments", lambda **_kwargs: "ledger unavailable")
    item = _item()
    gather = ResumeGather(
        observation=ResumeObservation(
            work_item_id=_ITEM,
            status="ready",
            liveness_observed=True,
        ),
        anchor=None,
        branch=f"feat/{_ITEM}",
        earlier_run_ids=(_RUN,),
        workflow_name=None,
    )

    monkeypatch.setattr(routing, "released_for_recovery", lambda **_kwargs: True)
    monkeypatch.setattr(routing, "gather_resume", lambda **_kwargs: gather)
    routes = routing.route_recovery(
        args=argparse.Namespace(),
        repo=tmp_path,
        candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    route = routes.route_for(work_item_id=_ITEM)
    assert route is not None
    assert route.route == ROUTE_HELD
    assert route.hold is not None
    assert route.hold.measurements[0].detail == "ledger unavailable"


def test_a_run_that_is_not_a_cancelled_fabro_run_is_never_preserved_by_this_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the externally cancelled run reaches the tree leg through this entry point."""
    called: list[str] = []
    monkeypatch.setattr(preservation, "_preserve_tree", lambda **_: called.append("tree"))
    preservation.preserve_cancelled_janitor_green_tree(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_ITEM,
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_RUN,
        ),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert called == []

"""Workflow-kind policy for the retired implementation `pr` ACP adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_acp_publication_policy
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    ACP_PUBLICATION_POLICY_STAGE,
    GROOM_ONLY_ACP_NODES,
    IMPLEMENTATION_PR_NOT_APPLIED_REASON,
    implementation_pr_override_refusal,
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title=item_id,
        description="publication policy fixture",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_repository_pr_is_scoped_only_for_implementation() -> None:
    block: dict[str, object] = {
        "acp_nodes": {"pr": {"command": "legacy"}, "review": {"command": "review"}},
        "other": "preserved",
    }
    groom, groom_audit = scoped_repository_block(
        block=block,
        workflow_kind=WORKFLOW_KIND_GROOM,
    )
    assert groom is block
    assert groom_audit == ()
    untouched, untouched_audit = scoped_repository_block(
        block={"acp_nodes": "invalid-but-unrelated"},
        workflow_kind="implement",
    )
    assert untouched == {"acp_nodes": "invalid-but-unrelated"}
    assert untouched_audit == ()
    no_pr, no_pr_audit = scoped_repository_block(
        block={"acp_nodes": {"review": {"command": "review"}}},
        workflow_kind="implement",
    )
    assert no_pr == {"acp_nodes": {"review": {"command": "review"}}}
    assert no_pr_audit == ()
    implementation, audit = scoped_repository_block(
        block=block,
        workflow_kind="implement",
    )
    assert implementation == {
        "acp_nodes": {"review": {"command": "review"}},
        "other": "preserved",
    }
    assert block["acp_nodes"] != implementation["acp_nodes"]
    assert audit == (
        {
            "layer": "repository",
            "node": "pr",
            "reason": IMPLEMENTATION_PR_NOT_APPLIED_REASON,
        },
    )
    assert {"pr"} == GROOM_ONLY_ACP_NODES


def test_dispatch_pr_override_refuses_only_an_implementation_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []

    def preview(*, repo: Path, work_item_id: str, name: str | None) -> str:
        assert repo == tmp_path
        seen.append((work_item_id, name))
        return "groom" if work_item_id.endswith("groom") else "implement"

    monkeypatch.setattr(
        _dispatcher_acp_publication_policy,
        "previewed_workflow_variant",
        preview,
    )
    monkeypatch.setattr(
        _dispatcher_acp_publication_policy,
        "is_groom_variant",
        lambda *, repo, variant: repo == tmp_path and variant == "groom",
    )
    journal = _Journal()
    irrelevant = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("review=uvx review",), workflow_name=None),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-implement"),),
        journal=journal,
    )
    assert irrelevant is None
    assert seen == []
    groom = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("pr",), workflow_name="groom-work"),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-groom"),),
        journal=journal,
    )
    assert groom is None
    assert journal.records == []
    refusal = implementation_pr_override_refusal(
        args=argparse.Namespace(acp_node=("pr=uvx forbidden",), workflow_name="selected"),
        repo=tmp_path,
        items=(_item(item_id="bd-ib-z"), _item(item_id="bd-ib-a")),
        journal=journal,
    )
    assert isinstance(refusal, str)
    assert "command stage" in refusal
    assert "bd-ib-a, bd-ib-z" in refusal
    assert seen[-2:] == [("bd-ib-z", "selected"), ("bd-ib-a", "selected")]
    assert journal.records == [
        {
            "stage": ACP_PUBLICATION_POLICY_STAGE,
            "work_item_ids": ["bd-ib-a", "bd-ib-z"],
            "result": "refused",
            "layer": "dispatch",
            "node": "pr",
            "reason": refusal,
        }
    ]

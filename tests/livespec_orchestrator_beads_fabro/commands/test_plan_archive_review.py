"""Plan archive membership-helper coverage.

The evidence record's own coverage moved with it, into
`test_plan_completeness_evidence.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_PARENT_CHILD,
    BeadsClient,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
    archive_completeness_review_request,
    has_blocks_edge_to_epic,
    is_blocks_edge_to_epic,
    undisposed_plan_child_ids,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _draft(*, issue_id: str, parent_id: str | None) -> IssueDraft:
    return IssueDraft(
        issue_id=issue_id,
        issue_type="task",
        title="child",
        description="child work",
        assignee=None,
        created_at="2026-08-11T00:00:00Z",
        parent_id=parent_id,
        metadata={"rank": "a1"},
        labels=["origin:freeform"],
    )


def test_archive_review_request_carries_closed_children_and_research_files(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-closed", parent_id="bd-ib-epic"))
    _fake().close_issue(issue_id="bd-ib-closed", reason="completed")
    source = tmp_path / "plan" / "archive-thread"
    research = source / "research"
    research.mkdir(parents=True)
    (research / "initial.md").write_text("research\n", encoding="utf-8")
    (research / "nested").mkdir()
    (research / "nested" / "detail.md").write_text("detail\n", encoding="utf-8")

    request = archive_completeness_review_request(
        client=_fake(),
        project_root=tmp_path,
        source=source,
        slug="archive-thread",
        epic_id="bd-ib-epic",
    )

    assert request.child_ids == ("bd-ib-closed",)
    assert request.research_paths == (
        "plan/archive-thread/research/initial.md",
        "plan/archive-thread/research/nested/detail.md",
    )


def test_archive_review_request_allows_missing_research_directory(tmp_path: Path) -> None:
    reset_fake_singleton()

    request = archive_completeness_review_request(
        client=_fake(),
        project_root=tmp_path,
        source=tmp_path / "plan" / "archive-thread",
        slug="archive-thread",
        epic_id="bd-ib-epic",
    )

    assert request.child_ids == ()
    assert request.research_paths == ()


def test_child_disposition_detects_parent_and_epic_blocker_edges() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-epic", parent_id=None))
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-parent", parent_id="bd-ib-epic"))
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-blocker", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-epic",
        to_id="bd-ib-blocker",
        edge_type=EDGE_BLOCKS,
    )
    _fake().update_issue(issue_id="bd-ib-parent", status="ready")
    _fake().update_issue(issue_id="bd-ib-blocker", status="ready")

    assert undisposed_plan_child_ids(client=_fake(), epic_id="bd-ib-epic") == (
        "bd-ib-blocker",
        "bd-ib-parent",
    )


def test_child_disposition_ignores_downstream_epic_depending_on_foundation() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-foundation", parent_id=None))
    _ = _fake().create_issue(
        draft=_draft(issue_id="bd-ib-finished-child", parent_id="bd-ib-foundation")
    )
    _fake().close_issue(issue_id="bd-ib-finished-child", reason="completed")
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-downstream", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-downstream",
        to_id="bd-ib-foundation",
        edge_type=EDGE_BLOCKS,
    )
    _fake().update_issue(issue_id="bd-ib-downstream", status="backlog")

    assert undisposed_plan_child_ids(client=_fake(), epic_id="bd-ib-foundation") == ()


class _RawChildrenClient:
    def list_issues(self) -> list[dict[str, object]]:
        return [
            {
                "id": "bd-ib-plain",
                "status": "backlog",
                "dependencies": [
                    {"depends_on_id": "bd-ib-epic", "type": EDGE_PARENT_CHILD},
                ],
            },
        ]


def test_child_disposition_detects_raw_parent_child_record() -> None:
    client = cast("BeadsClient", _RawChildrenClient())

    assert undisposed_plan_child_ids(client=client, epic_id="bd-ib-epic") == ("bd-ib-plain",)


def test_child_disposition_detects_parent_child_dependency_edge_without_readiness_gate() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-epic", parent_id=None))
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-child",
        to_id="bd-ib-epic",
        edge_type=EDGE_PARENT_CHILD,
    )
    _fake().update_issue(issue_id="bd-ib-child", status="ready")

    assert undisposed_plan_child_ids(client=_fake(), epic_id="bd-ib-epic") == ("bd-ib-child",)


def test_edge_predicates_ignore_malformed_records() -> None:
    assert not has_blocks_edge_to_epic(record={"dependencies": "not-a-list"}, epic_id="bd-ib-epic")
    assert not is_blocks_edge_to_epic(edge="not-an-edge", epic_id="bd-ib-epic")

"""Tests for the in-memory beads client."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import EDGE_BLOCKS, IssueDraft
from livespec_orchestrator_beads_fabro._beads_client_fake import FakeBeadsClient
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError


def _draft(**overrides: object) -> IssueDraft:
    base: dict[str, object] = {
        "issue_id": "li-a",
        "issue_type": "task",
        "title": "title",
        "description": "desc",
        "priority": 2,
        "assignee": None,
        "created_at": "2026-05-19T00:00:00Z",
    }
    base.update(overrides)
    return IssueDraft(**base)  # type: ignore[arg-type]


def test_fake_create_and_show() -> None:
    fake = FakeBeadsClient()
    returned = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert returned == "li-x"
    record = fake.show_issue(issue_id="li-x")
    assert record["id"] == "li-x"
    assert record["status"] == "open"


def test_fake_list_returns_copies() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    records = fake.list_issues()
    records[0]["status"] = "mutated"
    assert fake.show_issue(issue_id="li-x")["status"] == "open"


def test_fake_exists() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert fake.exists(issue_id="li-x") is True
    assert fake.exists(issue_id="li-absent") is False


def test_fake_show_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        _ = fake.show_issue(issue_id="li-absent")


def test_fake_update_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.update_issue(issue_id="li-absent", status="closed")


def test_fake_close_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.close_issue(issue_id="li-absent", reason="x")


def test_fake_add_dependency_missing_from_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.add_dependency(from_id="li-absent", to_id="li-y", edge_type=EDGE_BLOCKS)


def test_fake_add_comment_round_trips_via_list_comments() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.add_comment(issue_id="li-x", body="recurrence x2 on wave w7")
    bodies = [comment["text"] for comment in fake.list_comments(issue_id="li-x")]
    assert bodies == ["recurrence x2 on wave w7"]


def test_fake_add_comment_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.add_comment(issue_id="li-absent", body="orphan comment")


def test_fake_update_applies_all_fields() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.update_issue(
        issue_id="li-x",
        status="closed",
        parent_id="li-epic",
        add_labels=["resolution:completed", "resolution:completed"],
        metadata={"k": "v"},
    )
    record = fake.show_issue(issue_id="li-x")
    assert record["status"] == "closed"
    assert record["parent_id"] == "li-epic"
    assert record["labels"].count("resolution:completed") == 1
    assert record["metadata"] == {"k": "v"}


def test_fake_close_sets_status_and_reason() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.close_issue(issue_id="li-x", reason="shipped")
    record = fake.show_issue(issue_id="li-x")
    assert record["status"] == "closed"
    assert record["close_reason"] == "shipped"


def test_fake_add_dependency_dedupes() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.add_dependency(from_id="li-x", to_id="li-y", edge_type=EDGE_BLOCKS)
    fake.add_dependency(from_id="li-x", to_id="li-y", edge_type=EDGE_BLOCKS)
    record = fake.show_issue(issue_id="li-x")
    assert record["dependencies"] == [{"depends_on_id": "li-y", "type": EDGE_BLOCKS}]


def test_fake_children_filters_by_parent() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-child", parent_id="li-epic"))
    _ = fake.create_issue(draft=_draft(issue_id="li-other", parent_id=None))
    children = fake.children(parent_id="li-epic")
    assert [record["id"] for record in children] == ["li-child"]


def test_fake_seed_and_list_comments_roundtrip() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.seed_comment(
        issue_id="li-x",
        text="first rider",
        author="operator",
        created_at="2026-06-12T00:00:00Z",
    )
    fake.seed_comment(issue_id="li-x", text="second rider")
    records = fake.list_comments(issue_id="li-x")
    assert [record["text"] for record in records] == ["first rider", "second rider"]
    assert records[0]["author"] == "operator"
    assert records[0]["created_at"] == "2026-06-12T00:00:00Z"
    assert records[1]["author"] is None
    assert records[1]["created_at"] is None


def test_fake_list_comments_returns_copies() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.seed_comment(issue_id="li-x", text="original")
    records = fake.list_comments(issue_id="li-x")
    records[0]["text"] = "mutated"
    assert fake.list_comments(issue_id="li-x")[0]["text"] == "original"


def test_fake_list_comments_empty_for_uncommented_issue() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert fake.list_comments(issue_id="li-x") == []


def test_fake_list_comments_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        _ = fake.list_comments(issue_id="li-absent")


def test_fake_seed_comment_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.seed_comment(issue_id="li-absent", text="orphan")

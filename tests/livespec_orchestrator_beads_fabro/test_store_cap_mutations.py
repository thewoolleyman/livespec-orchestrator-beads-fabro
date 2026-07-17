"""Tests for the per-item cap-override label store mutation."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro._store_cap_mutations import update_work_item_cap
from livespec_orchestrator_beads_fabro._store_mutations import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _item(*, id_: str) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status="ready",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_update_work_item_cap_sets_then_replaces_the_prefixed_label() -> None:
    append_work_item(path=_config(), item=_item(id_="li-cap"))
    # First set: no prior cap label, so nothing is removed, only the label added.
    update_work_item_cap(
        path=_config(), item_id="li-cap", label_prefix="review-fix-cap:", value="2"
    )
    record = _fake().show_issue(issue_id="li-cap")
    assert "review-fix-cap:2" in record["labels"]
    assert "origin:freeform" in record["labels"]
    # Replace: the prior label is discovered by prefix, removed, and the new one added.
    update_work_item_cap(
        path=_config(), item_id="li-cap", label_prefix="review-fix-cap:", value="5"
    )
    record = _fake().show_issue(issue_id="li-cap")
    assert "review-fix-cap:5" in record["labels"]
    assert "review-fix-cap:2" not in record["labels"]
    assert "origin:freeform" in record["labels"]


def test_update_work_item_cap_leaves_non_string_labels_untouched() -> None:
    append_work_item(path=_config(), item=_item(id_="li-cap-mixed"))
    # A non-string label entry must be ignored by the prefix scan, not crash it.
    _fake().show_issue(issue_id="li-cap-mixed")["labels"].append(123)
    update_work_item_cap(
        path=_config(),
        item_id="li-cap-mixed",
        label_prefix="merge-on-review-cap:",
        value="true",
    )
    record = _fake().show_issue(issue_id="li-cap-mixed")
    assert "merge-on-review-cap:true" in record["labels"]
    assert 123 in record["labels"]


def test_update_work_item_cap_none_value_clears_the_label() -> None:
    append_work_item(path=_config(), item=_item(id_="li-cap-clear"))
    update_work_item_cap(
        path=_config(), item_id="li-cap-clear", label_prefix="review-fix-cap:", value="7"
    )
    assert "review-fix-cap:7" in _fake().show_issue(issue_id="li-cap-clear")["labels"]
    # A None value removes any prefixed label and adds none (clear-to-inherit).
    update_work_item_cap(
        path=_config(), item_id="li-cap-clear", label_prefix="review-fix-cap:", value=None
    )
    labels = _fake().show_issue(issue_id="li-cap-clear")["labels"]
    assert not any(str(label).startswith("review-fix-cap:") for label in labels)
    assert "origin:freeform" in labels

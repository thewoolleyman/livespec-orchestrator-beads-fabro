"""Tests for failed AI-acceptance rework state persistence."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_acceptance_rework import (
    update_acceptance_failed_ai_passes,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
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


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-store-acceptance-rework",
        type="task",
        status="acceptance",
        title="Acceptance rework state",
        description="Persist failed AI acceptance passes.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_policy="ai-then-human",
    )


def test_update_acceptance_failed_ai_passes_persists_count_and_returns_labels() -> None:
    item = _item()
    append_work_item(path=_config(), item=item)
    make_beads_client(config=_config()).update_issue(
        issue_id=item.id,
        add_labels=["acceptance-rework-cap:3"],
    )

    first = update_acceptance_failed_ai_passes(path=_config(), item_id=item.id)
    second = update_acceptance_failed_ai_passes(path=_config(), item_id=item.id)

    record = make_beads_client(config=_config()).show_issue(issue_id=item.id)
    assert first.failed_ai_passes == 1
    assert second.failed_ai_passes == 2
    assert "acceptance-rework-cap:3" in second.raw_labels
    assert record["metadata"]["acceptance_failed_ai_passes"] == 2

"""Tests for the drive policy-edit human valve helper."""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._drive_policy_valve import set_policy
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-policy",
        type="task",
        status="pending-approval",
        title="A policy task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="manual",
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_set_policy_edits_admission_without_status_change() -> None:
    item = _item()
    append_work_item(path=_config(), item=item)

    result = set_policy(
        config=_config(),
        item=item,
        action_id=f"set-admission:{item.id}:auto",
        action="set-admission",
        value="auto",
    )

    assert result["status"] == "green"
    stored = _stored()[item.id]
    assert (stored.status, stored.admission_policy) == ("pending-approval", "auto")

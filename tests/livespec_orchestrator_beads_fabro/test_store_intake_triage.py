"""Coverage for the narrow intake-triage raw read.

The un-triaged-backlog attention lane needs two signals `WorkItem` cannot
carry — the `intake:triaged` marker label and the beads-native `priority`
column — so this reader goes back to the raw record. Its reads are
fail-soft by design: a malformed record is skipped, never fatal, because a
single bad row must not blank an operator's whole attention list. The
strict path that surfaces a malformed record as an error stays
`store.read_work_items`.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_intake_triage import _triage_record
from livespec_orchestrator_beads_fabro.store import (
    INTAKE_TRIAGED_LABEL,
    IntakeTriageRecord,
    read_intake_triage_records,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(*, issue_id: str, priority: int, labels: list[str], status: str) -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=f"{issue_id} title",
            description="d",
            priority=priority,
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            labels=list(labels),
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=issue_id, status=status)


def _well_formed(**overrides: Any) -> BeadsRecord:
    """A minimal usable raw record, plus any per-case field overrides."""
    record: BeadsRecord = {"id": "bd-1", "title": "t", "status": "backlog"}
    record.update(overrides)
    return record


def _reduced(*, record: BeadsRecord) -> IntakeTriageRecord:
    """Reduce a record the case asserts IS usable, narrowing away the None."""
    result = _triage_record(record=record)
    assert result is not None
    return result


def test_read_intake_triage_records_reports_marker_priority_and_livespec_status() -> None:
    _seed(issue_id="bd-gated", priority=1, labels=[INTAKE_TRIAGED_LABEL], status="backlog")
    _seed(issue_id="bd-raw", priority=0, labels=[], status="backlog")
    _seed(issue_id="bd-closed", priority=2, labels=[], status="closed")

    records = read_intake_triage_records(path=_config())

    assert [(r.id, r.priority, r.status, r.triaged) for r in records] == [
        ("bd-gated", 1, "backlog", True),
        ("bd-raw", 0, "backlog", False),
        # beads' built-in `closed` reads back as the livespec name `done`, so
        # callers compare against the same vocabulary `WorkItem.status` uses.
        ("bd-closed", 2, "done", False),
    ]


def test_triage_record_skips_a_record_missing_a_required_string_field() -> None:
    """A row with no usable id / title / status is dropped, not fatal."""
    assert _triage_record(record={"title": "t", "status": "backlog"}) is None
    assert _triage_record(record={"id": "bd-1", "status": "backlog"}) is None
    assert _triage_record(record={"id": "bd-1", "title": "t"}) is None


def test_triage_record_reads_an_unusable_priority_as_no_urgency_signal() -> None:
    """A missing, non-integer, or boolean priority carries no urgency tier.

    `bool` is a subclass of `int` in Python, so `True` would otherwise read
    back as priority 1 — a P1 conjured out of a malformed row.
    """
    assert _reduced(record=_well_formed()).priority is None
    assert _reduced(record=_well_formed(priority="0")).priority is None
    assert _reduced(record=_well_formed(priority=True)).priority is None
    assert _reduced(record=_well_formed(priority=0)).priority == 0


def test_triage_record_reads_a_malformed_label_column_as_untriaged() -> None:
    """Labels that are not a list of strings never fake the marker's presence."""
    assert _reduced(record=_well_formed(labels="not-a-list")).triaged is False
    assert _reduced(record=_well_formed(labels=[7, None])).triaged is False
    assert _reduced(record=_well_formed(labels=[7, INTAKE_TRIAGED_LABEL])).triaged is True

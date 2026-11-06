"""Tests for legacy metadata content-field migration helpers.

The migration's payload omits the two retired metadata keys, and a metadata
write merges top-level keys, so the copies stay on the record (bd-ib-anwf).
These cases state what the tenant holds after a run, which is the native
backfill and the copies still in place, and what a second run then reports.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.store import (
    backfill_native_content_fields,
    read_work_items,
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


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _draft(*, issue_id: str, metadata: dict[str, object]) -> IssueDraft:
    return IssueDraft(
        issue_id=issue_id,
        issue_type="task",
        title="title",
        description="description",
        assignee=None,
        created_at="2026-05-19T00:00:00Z",
        metadata=metadata,
    )


class _StubClient:
    def __init__(self, *, records: list[dict[str, object]]) -> None:
        self.records = records

    def list_issues(self) -> list[dict[str, object]]:
        return [dict(record) for record in self.records]


def test_backfills_metadata_only_content_to_native_fields() -> None:
    client = _fake()
    _ = client.create_issue(
        draft=_draft(
            issue_id="li-legacy",
            metadata={
                "rank": "a0",
                "acceptance_criteria": "Legacy acceptance.",
                "notes": "Legacy notes.",
            },
        )
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 1
    record = client.show_issue(issue_id="li-legacy")
    assert record["acceptance_criteria"] == "Legacy acceptance."
    assert record["notes"] == "Legacy notes."
    assert record["metadata"] == {
        "rank": "a0",
        "acceptance_criteria": "Legacy acceptance.",
        "notes": "Legacy notes.",
    }
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.acceptance_criteria == "Legacy acceptance."
    assert read_back.notes == "Legacy notes."


def test_stale_metadata_never_overwrites_native_content() -> None:
    client = _fake()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="li-diverged",
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            metadata={
                "rank": "a0",
                "acceptance_criteria": "Stale acceptance.",
                "notes": "Stale notes.",
            },
            acceptance_criteria="Native acceptance.",
            notes="Native notes.",
        )
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 1
    record = client.show_issue(issue_id="li-diverged")
    assert record["acceptance_criteria"] == "Native acceptance."
    assert record["notes"] == "Native notes."
    assert record["metadata"] == {
        "rank": "a0",
        "acceptance_criteria": "Stale acceptance.",
        "notes": "Stale notes.",
    }
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.acceptance_criteria == "Native acceptance."
    assert read_back.notes == "Native notes."


def test_explicit_empty_native_content_is_kept_and_read_without_fallback() -> None:
    client = _fake()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="li-empty",
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            metadata={
                "rank": "a0",
                "acceptance_criteria": "Stale acceptance.",
                "notes": "Stale notes.",
            },
            acceptance_criteria="",
            notes="",
        )
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 1
    record = client.show_issue(issue_id="li-empty")
    assert record["acceptance_criteria"] == ""
    assert record["notes"] == ""
    assert record["metadata"] == {
        "rank": "a0",
        "acceptance_criteria": "Stale acceptance.",
        "notes": "Stale notes.",
    }
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.acceptance_criteria == ""
    assert read_back.notes == ""


def test_backfill_skips_rows_without_migratable_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubClient(
        records=[
            {"id": 99, "metadata": {"acceptance_criteria": "ignored"}},
            {"id": "li-nondict", "metadata": "not-a-dict"},
            {"id": "li-rank", "metadata": {"rank": "a0"}},
        ]
    )

    def make_stub_client(*, config: StoreConfig) -> _StubClient:
        _ = config
        return stub

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._store_content_migration.make_beads_client",
        make_stub_client,
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 0


def test_non_string_legacy_content_gets_no_native_backfill() -> None:
    client = _fake()
    _ = client.create_issue(
        draft=_draft(
            issue_id="li-nonstr",
            metadata={"rank": "a0", "acceptance_criteria": 42, "notes": False},
        )
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 1
    record = client.show_issue(issue_id="li-nonstr")
    assert "acceptance_criteria" not in record
    assert "notes" not in record
    assert record["metadata"] == {"rank": "a0", "acceptance_criteria": 42, "notes": False}


def test_a_second_run_backfills_nothing_and_counts_the_kept_copies_again() -> None:
    """The known gap of bd-ib-anwf, stated: the count is not idempotent.

    The first run backfills the native fields. The copies stay, because the
    payload only omits them, so the second run finds them again, writes
    nothing that changes the record, and still reports the row.
    """
    client = _fake()
    _ = client.create_issue(
        draft=_draft(
            issue_id="li-twice",
            metadata={"rank": "a0", "acceptance_criteria": "Legacy acceptance."},
        )
    )

    first = backfill_native_content_fields(path=_config())
    after_first = client.show_issue(issue_id="li-twice")
    second = backfill_native_content_fields(path=_config())

    assert (first, second) == (1, 1)
    assert client.show_issue(issue_id="li-twice") == after_first
    assert after_first["acceptance_criteria"] == "Legacy acceptance."
    assert after_first["metadata"] == {"rank": "a0", "acceptance_criteria": "Legacy acceptance."}


def test_backfill_writes_nothing_to_a_record_that_carries_no_metadata_copy() -> None:
    client = _fake()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="li-native",
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            metadata={"rank": "a0"},
            acceptance_criteria="Native acceptance.",
            notes="Native notes.",
        )
    )

    changed = backfill_native_content_fields(path=_config())

    assert changed == 0
    assert client.show_issue(issue_id="li-native")["metadata"] == {"rank": "a0"}

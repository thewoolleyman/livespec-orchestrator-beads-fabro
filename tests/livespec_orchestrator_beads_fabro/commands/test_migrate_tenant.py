"""Tests for the migrate-tenant end-to-end onboarding command.

The hermetic fake backend stands in for a scratch tenant. The test seeds
legacy heads directly through the fake's native records so pre-migration
`priority` values are present while `metadata.rank` is absent, then drives
the public command once and verifies both bootstrap steps.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands.migrate_tenant import main
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL, n_keys_between


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


@pytest.fixture(autouse=True)
def _in_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _legacy_head(*, id_: str, priority: int, captured_at: str, status: str = "ready") -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=id_,
            issue_type="task",
            title=f"{id_} title",
            description="legacy",
            priority=priority,
            assignee=None,
            created_at=captured_at,
        )
    )
    client.update_issue(issue_id=id_, status=status)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_main_registers_statuses_and_backfills_legacy_rank_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _legacy_head(id_="late-low", priority=2, captured_at="2026-01-01T00:00:00Z")
    _legacy_head(id_="newer-high", priority=0, captured_at="2026-01-02T00:00:00Z")
    _legacy_head(id_="older-high", priority=0, captured_at="2026-01-01T00:00:00Z")
    _legacy_head(id_="closed", priority=0, captured_at="2026-01-01T00:00:00Z", status="closed")

    assert _stored()["older-high"].rank == BOTTOM_SENTINEL

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "statuses registered" in captured.out
    assert "re-keyed 3 live work-item(s)" in captured.out
    assert make_beads_client(config=_config()).custom_statuses_registered is True

    stored = _stored()
    keys = n_keys_between(a=None, b=None, n=3)
    assert stored["older-high"].rank == keys[0]
    assert stored["newer-high"].rank == keys[1]
    assert stored["late-low"].rank == keys[2]
    assert stored["closed"].rank == BOTTOM_SENTINEL

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "re-keyed 0 live work-item(s)" in captured.out
    assert _stored() == stored


def test_main_backfills_dispatch_factory_metadata_from_legacy_comments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _legacy_head(id_="live", priority=0, captured_at="2026-01-01T00:00:00Z")
    _legacy_head(id_="closed", priority=0, captured_at="2026-01-01T00:00:00Z", status="closed")
    _fake().seed_comment(issue_id="live", text="livespec-dispatch-factory: hp")
    _fake().seed_comment(issue_id="closed", text="livespec-dispatch-factory: remote")

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "dispatch factories backfilled: 1" in captured.out
    assert _fake().show_issue(issue_id="live")["metadata"]["dispatch_factory"] == "hp"
    assert "dispatch_factory" not in _fake().show_issue(issue_id="closed")["metadata"]

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "dispatch factories backfilled: 0" in captured.out


def test_main_backfills_native_content_fields_and_keeps_the_metadata_copies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _fake()
    _legacy_head(id_="metadata-only", priority=0, captured_at="2026-01-01T00:00:00Z")
    client.update_issue(
        issue_id="metadata-only",
        metadata={
            "acceptance_criteria": "Legacy acceptance.",
            "notes": "Legacy notes.",
        },
    )
    _legacy_head(id_="diverged", priority=0, captured_at="2026-01-01T00:00:01Z")
    client.update_issue(
        issue_id="diverged",
        acceptance_criteria="Native acceptance.",
        notes="Native notes.",
        metadata={
            "rank": "a1",
            "acceptance_criteria": "Stale acceptance.",
            "notes": "Stale notes.",
        },
    )

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "native content fields backfilled: 2" in captured.out
    metadata_only = client.show_issue(issue_id="metadata-only")
    assert metadata_only["acceptance_criteria"] == "Legacy acceptance."
    assert metadata_only["notes"] == "Legacy notes."
    # The metadata copies stay: the backfill's payload only omits them, and a
    # metadata write merges top-level keys (bd-ib-anwf).
    assert metadata_only["metadata"] == {
        "rank": "a0",
        "acceptance_criteria": "Legacy acceptance.",
        "notes": "Legacy notes.",
    }
    diverged = client.show_issue(issue_id="diverged")
    assert diverged["acceptance_criteria"] == "Native acceptance."
    assert diverged["notes"] == "Native notes."
    assert diverged["metadata"] == {
        "rank": "a1",
        "acceptance_criteria": "Stale acceptance.",
        "notes": "Stale notes.",
    }

    rc = main(argv=[])
    captured = capsys.readouterr()

    # Both rows are counted again because their copies are still there. The
    # second run's writes change neither record.
    assert rc == 0
    assert "native content fields backfilled: 2" in captured.out
    assert client.show_issue(issue_id="metadata-only") == metadata_only
    assert client.show_issue(issue_id="diverged") == diverged

"""Focused dispatch-factory marker and dispatch run-stamp tests."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_factory import (
    dispatch_run_id_from_record,
    dispatch_run_ids_for,
    dispatch_run_metadata,
    record_dispatch_run,
)
from livespec_orchestrator_beads_fabro.store import (
    dispatch_factory_for,
    dispatch_factory_from_record,
    record_dispatch_factory,
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


def _issue(*, issue_id: str) -> None:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
        )
    )


def test_dispatch_factory_falls_back_to_legacy_comments() -> None:
    _issue(issue_id="li-aaa111")
    _fake().seed_comment(issue_id="li-aaa111", text="livespec-dispatch-factory: ")
    _fake().seed_comment(issue_id="li-aaa111", text="livespec-dispatch-factory: hp")

    assert dispatch_factory_for(path=_config(), work_item_id="li-aaa111") == "hp"


def test_dispatch_factory_from_record_ignores_malformed_metadata() -> None:
    assert dispatch_factory_from_record(record={"metadata": "not-json-object"}) is None


def _metadata_of(*, issue_id: str) -> dict[str, Any]:
    raw = _fake().show_issue(issue_id=issue_id).get("metadata")
    assert isinstance(raw, dict)
    return dict(raw)


def test_record_dispatch_run_stamps_the_run_id_and_factory_at_the_top_level() -> None:
    _issue(issue_id="li-run001")

    record_dispatch_run(
        path=_config(),
        work_item_id="li-run001",
        run_id="01M199TWET07",
        factory_name="hp",
        factory_server="https://hp-xubuntu.perch-rudd.ts.net:32276",
    )

    metadata = _metadata_of(issue_id="li-run001")
    assert metadata["dispatch_fabro_run_id"] == "01M199TWET07"
    assert metadata["dispatch_factory"] == {
        "name": "hp",
        "server": "https://hp-xubuntu.perch-rudd.ts.net:32276",
    }


def test_record_dispatch_run_preserves_unmodeled_top_level_and_nested_metadata() -> None:
    _issue(issue_id="li-run002")
    _fake().update_issue(
        issue_id="li-run002",
        metadata={
            "rank": "a0",
            "unmodeled_top_level": "survives",
            "audit": {"supersedes": "li-old", "captured_at": "2026-08-30T00:00:00Z"},
        },
    )

    record_dispatch_run(
        path=_config(),
        work_item_id="li-run002",
        run_id="01NEW",
        factory_name="vps",
        factory_server=None,
    )

    metadata = _metadata_of(issue_id="li-run002")
    assert metadata["rank"] == "a0"
    assert metadata["unmodeled_top_level"] == "survives"
    assert metadata["audit"] == {"supersedes": "li-old", "captured_at": "2026-08-30T00:00:00Z"}
    assert metadata["dispatch_fabro_run_id"] == "01NEW"
    assert metadata["dispatch_factory"] == {"name": "vps", "server": None}


def test_a_second_dispatch_overwrites_the_run_id_with_the_newer_run() -> None:
    _issue(issue_id="li-run003")

    for run_id in ("01OLDRUN", "01NEWRUN"):
        record_dispatch_run(
            path=_config(),
            work_item_id="li-run003",
            run_id=run_id,
            factory_name="hp",
            factory_server="https://hp:32276",
        )

    assert _metadata_of(issue_id="li-run003")["dispatch_fabro_run_id"] == "01NEWRUN"


def test_the_stamped_factory_object_still_answers_the_pinned_factory_name() -> None:
    """The stamp must not blind the retry pinning that shares its metadata key."""
    _issue(issue_id="li-run004")
    record_dispatch_factory(path=_config(), work_item_id="li-run004", factory="hp")

    record_dispatch_run(
        path=_config(),
        work_item_id="li-run004",
        run_id="01PIN",
        factory_name="hp",
        factory_server="https://hp:32276",
    )

    assert dispatch_factory_for(path=_config(), work_item_id="li-run004") == "hp"


def test_dispatch_run_ids_for_maps_each_stamped_run_to_its_work_item() -> None:
    _issue(issue_id="li-run005")
    _issue(issue_id="li-run006")
    record_dispatch_run(
        path=_config(),
        work_item_id="li-run005",
        run_id="01FIVE",
        factory_name="hp",
        factory_server=None,
    )

    mapped = dispatch_run_ids_for(path=_config())

    assert mapped["01FIVE"] == "li-run005"
    assert "li-run006" not in mapped.values()


def test_dispatch_run_id_from_record_ignores_a_blank_or_absent_stamp() -> None:
    assert dispatch_run_id_from_record(record={"metadata": {"dispatch_fabro_run_id": "  "}}) is None
    assert dispatch_run_id_from_record(record={"metadata": {}}) is None


def test_dispatch_factory_from_record_ignores_an_object_carrying_no_name() -> None:
    assert dispatch_factory_from_record(record={"metadata": {"dispatch_factory": {}}}) is None


def test_the_run_stamp_overlay_is_the_two_top_level_keys_a_reader_finds_the_stamp_under() -> None:
    """The overlay a token-guarded stamp merges reads back as the run it carries."""
    overlay = dispatch_run_metadata(run_id="01RUN", factory_name="hp", factory_server=None)

    assert overlay == {
        "dispatch_fabro_run_id": "01RUN",
        "dispatch_factory": {"name": "hp", "server": None},
    }
    assert dispatch_run_id_from_record(record={"metadata": overlay}) == "01RUN"
    assert dispatch_factory_from_record(record={"metadata": overlay}) == "hp"

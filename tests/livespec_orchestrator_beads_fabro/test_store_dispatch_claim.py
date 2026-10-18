"""The dispatch claim stamp: one metadata key, read and written whole.

The reader's arms are all the shapes a record an EARLIER build wrote can have,
and each one is asserted because the alternative to reporting them is raising
mid-survey: a reconciler that crashed on one legacy row would stop surveying
every row after it.

The writer's one assertion is that it does not destroy its neighbours. `bd
update --metadata` merges top-level keys and REPLACES a nested object
wholesale, so the stamp's own object is safe to write whole — and the keys
BESIDE it are safe only because the write resends the whole mapping it read.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    ClaimStamp,
    claim_row_for,
    claim_stamp_from_record,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-claimstamp"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"metadata": "not-a-mapping"},
        {"metadata": {}},
        {"metadata": {CLAIM_STAMP_METADATA_KEY: "not-a-mapping"}},
    ],
)
def test_a_record_carrying_no_readable_stamp_reports_none(*, record: dict[str, object]) -> None:
    assert claim_stamp_from_record(record=record) is None


def test_every_field_of_an_unreadable_stamp_reports_none_rather_than_raising() -> None:
    stamp = claim_stamp_from_record(
        record={
            "metadata": {
                CLAIM_STAMP_METADATA_KEY: {
                    "dispatch_id": "   ",
                    "dispatching_host": 7,
                    "run_id": "",
                    "factory": "not-a-mapping",
                }
            }
        }
    )

    assert stamp == ClaimStamp(
        dispatch_id=None,
        dispatching_host=None,
        run_id=None,
        factory_name=None,
        factory_server=None,
    )
    # No run id means PENDING, which is what keeps a freshly admitted dispatch
    # from being read as the previous claim.
    assert stamp is not None and stamp.pending


def test_a_populated_stamp_reads_back_field_for_field() -> None:
    stamp = claim_stamp_from_record(
        record={
            "metadata": {
                CLAIM_STAMP_METADATA_KEY: {
                    "dispatch_id": " 01DISPATCH ",
                    "dispatching_host": "hp",
                    "run_id": " 01RUN ",
                    "factory": {"name": " hp ", "server": " https://hp.example:32276 "},
                }
            }
        }
    )

    assert stamp == ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id="01RUN",
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )
    assert stamp is not None and not stamp.pending


def test_writing_the_stamp_preserves_every_other_metadata_key() -> None:
    append_work_item(path=_config(), item=_item())
    client = make_beads_client(config=_config())
    before = client.show_issue(issue_id=_ITEM_ID)
    neighbours = {
        key: value for key, value in dict(before["metadata"]).items() if key != "dispatch_claim"
    }
    assert neighbours != {}

    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="hp",
            run_id=None,
            factory_name="hp",
            factory_server=None,
        ),
    )

    after = dict(make_beads_client(config=_config()).show_issue(issue_id=_ITEM_ID)["metadata"])
    assert {key: after[key] for key in neighbours} == neighbours
    assert after[CLAIM_STAMP_METADATA_KEY] == {
        "dispatch_id": "01DISPATCH",
        "dispatching_host": "hp",
        "run_id": None,
        "factory": {"name": "hp", "server": None},
    }


def test_a_pending_stamp_is_replaced_wholesale_by_the_run_stamp() -> None:
    append_work_item(path=_config(), item=_item())
    pending = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id=None,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=pending)

    record_claim_stamp(
        path=_config(), work_item_id=_ITEM_ID, stamp=replace(pending, run_id="01RUN")
    )

    row = claim_row_for(path=_config(), work_item_id=_ITEM_ID)
    assert (row.status, row.assignee) == ("active", "fabro")
    assert row.stamp == replace(pending, run_id="01RUN")

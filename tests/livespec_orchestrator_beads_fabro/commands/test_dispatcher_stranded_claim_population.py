"""Which rows the stranded-claim survey grades: the edges of telling a handed-off rework from a parked one.

Covers `_dispatcher_stranded_claim_population` beside
`test_dispatcher_stranded_claim_handoff_rework.py`, which binds the four outcomes.
These are the readings that module's journeys cannot reach: a
journal that could not be read, a stamp that names no run, and a marked row with
no stamp at all. Each answers PARKED, because the survey completes a claim only
on evidence it could read, and a parked rework costs one pass where a wrongly
completed one cannot be walked back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_handoff import (
    handed_off_rework_pull_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-reworkedges"
_OTHER_ID = "bd-ib-someoneelse"
_RUN_ID = "01EDGERUN"
_PR = 4800


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
        title="A marked row",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        rework_pending=True,
    )


def _rows(*, item_id: str = _ITEM_ID) -> tuple[dict[str, object], ...]:
    return (
        {"stage": "ledger-rework-admit", "work_item_id": item_id},
        {"stage": "dispatch-id", "work_item_id": item_id},
        {
            "stage": "merge-wait-handed-off",
            "work_item_id": item_id,
            "run_id": _RUN_ID,
            "pr_number": _PR,
        },
    )


def test_the_rework_handoff_is_read_off_the_rework_dispatch() -> None:
    assert (
        handed_off_rework_pull_request(records=_rows(), work_item_id=_ITEM_ID, run_id=_RUN_ID)
        == _PR
    )


def test_another_items_rework_handoff_is_not_this_items() -> None:
    assert (
        handed_off_rework_pull_request(
            records=_rows(item_id=_OTHER_ID), work_item_id=_ITEM_ID, run_id=_RUN_ID
        )
        is None
    )


def test_an_unreadable_journal_is_not_a_handed_off_rework() -> None:
    assert (
        handed_off_rework_pull_request(records=None, work_item_id=_ITEM_ID, run_id=_RUN_ID) is None
    )


def test_a_journal_with_no_rework_admission_is_not_a_handed_off_rework() -> None:
    assert (
        handed_off_rework_pull_request(records=_rows()[1:], work_item_id=_ITEM_ID, run_id=_RUN_ID)
        is None
    )


@pytest.mark.parametrize(
    "stamp",
    [
        None,
        ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="owning-host",
            run_id=None,
            factory_name="hp",
            factory_server="https://hp.example:32276",
        ),
    ],
    ids=["no-stamp", "stamp-names-no-run"],
)
def test_a_marked_row_whose_stamp_names_no_run_is_not_surveyed(
    tmp_path: Path, stamp: ClaimStamp | None
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    journal_path = repo / "tmp" / "journal.jsonl"
    journal_path.parent.mkdir(parents=True)
    _ = journal_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8"
    )
    append_work_item(path=_config(), item=_item())
    if stamp is not None:
        record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=stamp)

    survey = survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=(_item(),),
            journal=JournalFile(path=journal_path),
            runner=_NoRunner(),
            inventories=(
                FactoryInventory(
                    name="hp",
                    server_url="https://hp.example:32276",
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={},
                ),
            ),
            this_host="owning-host",
            now_iso="2026-11-09T09:00:00Z",
        )
    )

    assert (survey.recovered, survey.held) == ((), ())


class _NoRunner:
    run = staticmethod(lambda **_: pytest.fail("a parked rework must not reach the forge"))

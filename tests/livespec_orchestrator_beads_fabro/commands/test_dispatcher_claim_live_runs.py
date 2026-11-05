"""`dispatcher.wip_cap` counts only claims that still hold a factory run slot.

bd-ib-rtzhfc, measured 2026-11-05 ~04:15Z: the WIP count read 20/20 while
the petri board read 15/16. Ledger-active items whose stamped run had already
ended (they were in their post-run legs, still holding a live dispatch lock)
were counted as if they held a run slot. A claim whose current dispatch has
a stamped run that its factory no longer lists as live holds no slot. A claim
with no stamped run yet is still launching, so it keeps counting. A board
nobody can read never lowers the count.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, call

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_claim_live_runs as live_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_slots import (
    ready_free_slots,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_accounting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.types import WorkItem, WorkItemStatus

_FACTORY = "petri"


def test_a_claim_whose_stamped_run_has_ended_holds_no_wip_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = _item(item_id="bd-live-run")
    ended = _item(item_id="bd-post-run-legs")
    journal = _stamped_journal(repo=tmp_path, item_ids=(live.id, ended.id))
    board = Mock(return_value=frozenset({live.id}))
    monkeypatch.setattr(live_runs, "read_live_item_ids", board)

    accounting = claimed_active_accounting(repo=tmp_path, items=[live, ended], journal=journal)

    facts = [
        accounting.active_count == 1,
        accounting.live_lock_active_ids == (live.id,),
        getattr(accounting, "ended_run_active_ids", None) == (ended.id,),
        board.call_args_list == [call(repo=tmp_path, factory=_FACTORY)],
    ]
    assert all(facts)


def test_wip_cap_n_with_n_active_claims_and_fewer_live_runs_still_admits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = [_item(item_id=f"bd-claim-{index}") for index in range(3)]
    journal = _stamped_journal(repo=tmp_path, item_ids=tuple(claim.id for claim in claims))
    monkeypatch.setattr(
        live_runs, "read_live_item_ids", Mock(return_value=frozenset({claims[0].id}))
    )
    accounting = claimed_active_accounting(repo=tmp_path, items=claims, journal=journal)

    free = ready_free_slots(
        admittable=[_item(item_id="bd-next", status="ready")],
        occupied=accounting.active_count,
        wip_cap=len(claims),
        budget_left=None,
    )

    assert free == 2


def test_an_unreadable_board_never_lowers_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = [_item(item_id="bd-unread-a"), _item(item_id="bd-unread-b")]
    journal = _stamped_journal(repo=tmp_path, item_ids=tuple(claim.id for claim in claims))
    monkeypatch.setattr(live_runs, "read_live_item_ids", Mock(return_value=None))

    accounting = claimed_active_accounting(repo=tmp_path, items=claims, journal=journal)

    facts = [
        accounting.active_count == 2,
        getattr(accounting, "ended_run_active_ids", None) == (),
    ]
    assert all(facts)


def test_a_claim_with_no_stamped_run_since_its_admit_keeps_counting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launching = _item(item_id="bd-still-launching")
    _ = write_dispatch_lock(repo=tmp_path, work_item_id=launching.id, dispatch_id="d-launch")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record=_stamp(item_id=launching.id, run_id="01OLDRUN"))
    journal.append(record={"stage": "ledger-admit", "work_item_id": launching.id})
    board = Mock(return_value=frozenset())
    monkeypatch.setattr(live_runs, "read_live_item_ids", board)

    accounting = claimed_active_accounting(repo=tmp_path, items=[launching], journal=journal)

    facts = [accounting.active_count == 1, board.call_count == 0]
    assert all(facts)


def test_the_reader_names_the_items_whose_run_the_factory_lists_as_live(tmp_path: Path) -> None:
    lister = Mock()
    lister.list_runs = Mock(
        return_value=(
            _run(run_id="01LIVE", status_kind="running", item_id="bd-running"),
            _run(run_id="01DONE", status_kind="succeeded", item_id="bd-finished"),
            _run(run_id="01UNLABELLED", status_kind="running", item_id=None),
        )
    )

    live = live_runs.read_live_item_ids(repo=tmp_path, factory=_FACTORY, lister=lister)

    facts = [
        live == frozenset({"bd-running"}),
        lister.list_runs.call_args_list == [call(factory=_FACTORY)],
    ]
    assert all(facts)


def test_the_reader_reports_an_unreadable_board_as_none(tmp_path: Path) -> None:
    lister = Mock()
    lister.list_runs = Mock(return_value=None)

    live = live_runs.read_live_item_ids(repo=tmp_path, factory=_FACTORY, lister=lister)

    assert live is None


def _run(*, run_id: str, status_kind: str, item_id: str | None) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None,
        total_usd_micros=None,
        work_item_id=item_id,
    )


def _stamped_journal(*, repo: Path, item_ids: tuple[str, ...]) -> JournalFile:
    journal = JournalFile(path=repo / "journal.jsonl")
    for index, item_id in enumerate(item_ids):
        _ = write_dispatch_lock(repo=repo, work_item_id=item_id, dispatch_id=f"d-{index}")
        journal.append(record={"stage": "ledger-admit", "work_item_id": item_id})
        journal.append(record=_stamp(item_id=item_id, run_id=f"01RUN{index}"))
    return journal


def _stamp(*, item_id: str, run_id: str) -> dict[str, object]:
    return {
        "stage": "dispatch-run-stamp",
        "work_item_id": item_id,
        "run_id": run_id,
        "dispatch_factory": _FACTORY,
        "stamped": True,
    }


def _item(*, item_id: str, status: WorkItemStatus = "active") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        rework_pending=False,
        title="Claim",
        description="Dispatch claim fixture.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )

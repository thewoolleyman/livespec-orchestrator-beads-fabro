"""Coverage for the un-triaged-backlog attention lane.

The lane exists because a `backlog` work-item is invisible: no dispatch
surface admits it and, before this lane, no attention surface reported it.
An item filed with a raw `bd create` never runs the intake
Definition-of-Ready gate, so it lands there and stays there, looking exactly
like an epic the gate deliberately parked. These cases pin the
discriminator (the `intake:triaged` marker) and the noise control that keeps
the lane worth leaving switched on.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._needs_attention_untriaged_backlog import (
    untriaged_backlog_items,
)
from livespec_orchestrator_beads_fabro.store import IntakeTriageRecord


def _triage(
    *,
    id_: str,
    priority: int | None,
    status: str = "backlog",
    triaged: bool = False,
) -> IntakeTriageRecord:
    return IntakeTriageRecord(
        id=id_,
        title=f"{id_} title",
        status=status,
        priority=priority,
        triaged=triaged,
    )


def test_untriaged_backlog_items_orders_by_urgency_then_id(tmp_path: Path) -> None:
    """Deterministic order, and a record with no priority never displaces a P0.

    The tenant read order is whatever the backend hands back, so the lane
    imposes its own: urgency tier first, then id. A record carrying no usable
    native priority sorts after every real tier rather than ahead of them.
    """
    attention = untriaged_backlog_items(
        project_root=tmp_path,
        repo="repo",
        records=[
            _triage(id_="bd-none", priority=None),
            _triage(id_="bd-p1-b", priority=1),
            _triage(id_="bd-p0", priority=0),
            _triage(id_="bd-p1-a", priority=1),
        ],
    )

    assert [item.id for item in attention] == [
        "hygiene:untriaged-backlog:bd-p0",
        "hygiene:untriaged-backlog:bd-p1-a",
        "hygiene:untriaged-backlog:bd-p1-b",
        "hygiene:untriaged-backlog-remainder:count",
    ]
    assert "1 un-triaged backlog work-items at P2 or lower" in attention[-1].summary


def test_untriaged_backlog_items_collapses_the_lower_priority_remainder(tmp_path: Path) -> None:
    """The whole P2-or-lower tail is ONE item, never one per record.

    This is the load-bearing noise control: a repository carrying hundreds of
    un-triaged backlog items must not produce hundreds of attention items, or
    the lane gets turned off and takes the P0/P1 signal with it.
    """
    attention = untriaged_backlog_items(
        project_root=tmp_path,
        repo="repo",
        records=[_triage(id_=f"bd-{index}", priority=2) for index in range(40)],
    )

    assert [item.id for item in attention] == ["hygiene:untriaged-backlog-remainder:count"]
    assert "40 un-triaged backlog work-items at P2 or lower" in attention[0].summary


def test_untriaged_backlog_items_emits_nothing_when_every_backlog_item_is_triaged(
    tmp_path: Path,
) -> None:
    """Silence on a clean ledger — no remainder item when there is no remainder.

    A P0 item the gate DID see (marker present) is deliberately parked, and a
    P0 item in any other status belongs to another lane. Neither is reported
    here, even though both would be if the lane keyed on status alone.
    """
    attention = untriaged_backlog_items(
        project_root=tmp_path,
        repo="repo",
        records=[
            _triage(id_="bd-parked", priority=0, triaged=True),
            _triage(id_="bd-ready", priority=0, status="ready"),
            _triage(id_="bd-done", priority=0, status="done"),
        ],
    )

    assert attention == []


def test_untriaged_backlog_items_carry_runnable_repo_scoped_handoffs(tmp_path: Path) -> None:
    """Both lanes hand off a concrete shell command scoped to the repository."""
    attention = untriaged_backlog_items(
        project_root=tmp_path,
        repo="repo",
        records=[_triage(id_="bd-p0", priority=0), _triage(id_="bd-p4", priority=4)],
    )

    per_item, remainder = attention
    assert per_item.kind == "hygiene"
    assert per_item.urgency == "high"
    assert per_item.source_ref.work_item == "bd-p0"
    assert per_item.handoff.kind == "shell"
    assert "bd-p0" in per_item.handoff.command
    assert str(tmp_path) in per_item.handoff.command
    assert remainder.urgency == "low"
    # The summary lane names no single work-item — it stands for the whole tail.
    assert remainder.source_ref.work_item is None
    assert remainder.handoff.kind == "shell"
    assert str(tmp_path) in remainder.handoff.command
    assert "intake:triaged" in remainder.handoff.command

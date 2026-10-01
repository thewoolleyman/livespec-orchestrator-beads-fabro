"""Every disposing valve reaches the lifecycle seam's reconciliation chokepoint.

The point of these tests is not that the wrapper functions call the hook —
that is one line of code. It is that CLOSE, ACCEPT, MOVE, RESOLVE-BLOCKED and
RECONCILE-MERGED each reach it by driving the real valve, so a future valve
rewired back onto a raw store seam fails here rather than silently leaking a
held factory slot.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    _dispatcher_completion_close,
    _drive_policy_valves,
    _drive_valves,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_writes as lifecycle_writes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    "/_dispatcher_lifecycle_writes.py"
)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    # The proof leg the real pass carries. `None` is what a legacy-source item
    # resolves to, and it is the right stand-in here: these cases are about the
    # DISPOSITION the verdict routes to, and the pointer write skips an item
    # with no record rather than changing which branch runs.
    proof: None = None
    verdict: str = "PASS"
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {"stage": "acceptance-ai-pass", "work_item_id": work_item_id, "policy": policy}


def test_the_seam_module_exposes_one_entry_point_per_store_write() -> None:
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes"
    )

    assert sorted(module.__all__) == [
        "close_work_item_and_reconcile",
        "write_blocked_state_and_reconcile",
        "write_work_item_status_and_reconcile",
    ]


def test_the_close_valve_reaches_the_chokepoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)
    written = _stub_store_writes(monkeypatch=monkeypatch)
    monkeypatch.setattr(_dispatcher_completion_close, "store_config", lambda **_: _config())

    _dispatcher_completion_close.close_dispatch_item(
        repo=tmp_path,
        item=_item(status="active"),
        outcome=_outcome(),
        resolution="completed",
        reason="merged",
    )

    assert written == [("append", "bd-ib-1", "done")]
    assert reconciled == [("bd-ib-1", "done")]


def test_the_accept_valve_reaches_the_chokepoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)
    written = _stub_store_writes(monkeypatch=monkeypatch)
    _stub_valve_store(monkeypatch=monkeypatch, item=_item(status="acceptance"))

    result = _drive_valves.run_human_valve_action(repo=tmp_path, action_id="accept:bd-ib-1")

    assert result["status"] == "green"
    assert written == [("status", "bd-ib-1", "done")]
    assert reconciled == [("bd-ib-1", "done")]


def test_the_move_valve_reaches_the_chokepoint(monkeypatch: pytest.MonkeyPatch) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)
    written = _stub_store_writes(monkeypatch=monkeypatch)

    result = _drive_policy_valves.move_item(
        config=_config(),
        item=_item(status="active"),
        aid="move:bd-ib-1:backlog",
        target_status="backlog",
    )

    assert result["status"] == "green"
    assert written == [("status", "bd-ib-1", "backlog")]
    assert reconciled == [("bd-ib-1", "backlog")]


def test_the_resolve_blocked_valve_reaches_the_chokepoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)
    written = _stub_store_writes(monkeypatch=monkeypatch)

    result = _drive_policy_valves.resolve_blocked_item(
        config=_config(),
        item=_item(status="blocked", blocked_reason="needs-human"),
        aid="resolve-blocked:bd-ib-1:ready",
        target_status="ready",
    )

    assert result["status"] == "green"
    assert written == [("blocked-state", "bd-ib-1", "ready")]
    assert reconciled == [("bd-ib-1", "ready")]


def test_the_reconcile_merged_completion_reaches_the_chokepoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)
    written = _stub_store_writes(monkeypatch=monkeypatch)
    monkeypatch.setattr(_dispatcher_completion, "store_config", lambda **_: _config())
    monkeypatch.setattr(_dispatcher_completion, "close_dispatch_item", lambda **_: None)
    monkeypatch.setattr(_dispatcher_completion, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )

    _dispatcher_completion.complete_and_accept(
        repo=tmp_path,
        item=_item(status="active", acceptance_policy="ai-only"),
        outcome=_outcome(),
        journal=_Journal(),
    )

    assert written == [("status", "bd-ib-1", "acceptance")]
    assert reconciled == [("bd-ib-1", "acceptance")]


def test_the_chokepoint_runs_only_after_the_write_lands(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    def _write(**_: object) -> None:
        order.append("write")

    def _reconcile(*, path: StoreConfig, item_id: str, status: str) -> None:
        _ = (path, item_id, status)
        order.append("reconcile")

    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", _write)
    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", _reconcile)

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(), item_id="bd-ib-1", status="ready"
    )

    assert order == ["write", "reconcile"]


def test_a_write_that_raises_never_reconciles(monkeypatch: pytest.MonkeyPatch) -> None:
    reconciled = _spy_chokepoint(monkeypatch=monkeypatch)

    def _raise(**_: object) -> None:
        raise RuntimeError("tenant refused")

    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", _raise)

    with pytest.raises(RuntimeError):
        lifecycle_writes.write_work_item_status_and_reconcile(
            path=_config(), item_id="bd-ib-1", status="done"
        )

    assert reconciled == []


def _spy_chokepoint(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    def _record(*, path: StoreConfig, item_id: str, status: str) -> None:
        _ = path
        seen.append((item_id, status))

    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", _record)
    return seen


def _stub_store_writes(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Replace the three store seams the module writes through, recording each."""
    written: list[tuple[str, str, str]] = []

    def _append(*, path: StoreConfig, item: WorkItem) -> None:
        _ = path
        written.append(("append", item.id, item.status))

    def _status(*, path: StoreConfig, item_id: str, status: str, **_: object) -> None:
        _ = path
        written.append(("status", item_id, status))

    def _blocked(*, path: StoreConfig, item_id: str, status: str, **_: object) -> None:
        _ = path
        written.append(("blocked-state", item_id, status))

    monkeypatch.setattr(lifecycle_writes.store, "append_work_item", _append)
    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", _status)
    monkeypatch.setattr(lifecycle_writes, "update_work_item_blocked_state", _blocked)
    return written


def _stub_valve_store(*, monkeypatch: pytest.MonkeyPatch, item: WorkItem) -> None:
    monkeypatch.setattr(_drive_valves, "resolve_store_config", lambda **_: _config())
    monkeypatch.setattr(_drive_valves.store, "read_work_items", lambda **_: [])
    monkeypatch.setattr(_drive_valves, "_find_item", lambda **_: item, raising=False)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orchestrator-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orchestrator-beads-fabro",
        database="livespec-orchestrator-beads-fabro",
        bd_path="bd",
        fake=True,
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-1",
        status="green",
        stage="done",
        pr_number=1,
        merge_sha="abc123",
        detail="merged",
    )


def _item(*, status: str, **overrides: Any) -> WorkItem:
    return WorkItem(
        id="bd-ib-1",
        type="task",
        status=status,
        title="bd-ib-1",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        **overrides,
    )

"""Coverage for the journal-recorded half of the idle-slot audit's hold evidence.

The audit reads a hold from ledger status and from the shared admission verdict;
a `recovery-held` that only the dispatch journal records is the third source. It
applies to the tenant whose checkout is THIS repository and to no other, because
the journal read is this repository's own, so each case pairs the own-tenant
reading with a second tenant that must be left alone.
"""

import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_AUDIT_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit"
_HOLDS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_holds"
_JOURNAL_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_journal_hold"
_TENANTS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_tenants"
_BOARD_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"
_FACTORIES = {"hp": {"server": "https://hp.example:32276"}}


def _item(*, id_: str, status: str = "ready") -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, status=status)  # pyright: ignore[reportArgumentType]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_config(root: Path, *, priority: list[dict[str, object]]) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": _FACTORIES,
                        "idle_slot_audit": {"factory": "hp", "priority": priority},
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _journal(root: Path, *, records: list[dict[str, object]]) -> None:
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _reading(*, items: tuple[WorkItem, ...]) -> object:
    records = tuple({"id": item.id, "dependencies": []} for item in items)
    return importlib.import_module(_TENANTS_NAME).TenantReading(items=items, records=records)


def _board() -> Callable[..., object]:
    board = importlib.import_module(_BOARD_NAME).BoardReading(
        observable=True, live_count=0, queued_count=0, live_item_ids=frozenset()
    )

    def _read(*, repo: Path, factory: str) -> object:
        _ = (repo, factory)
        return board

    return _read


def _no_holds(*, repo: Path, items: list[WorkItem]) -> dict[str, str]:
    _ = (repo, items)
    return {}


def _audit(root: Path, *, readings: dict[Path, object], **extra: object) -> object:
    def _tenant(*, repo: Path) -> object:
        return readings.get(repo)

    return importlib.import_module(_AUDIT_NAME).idle_slot_audit(
        project_root=root,
        tenant_reader=_tenant,
        board_reader=_board(),
        hold_reader=_no_holds,
        **extra,
    )


def _children(result: object) -> dict[str, tuple[str, str | None]]:
    return {
        child.id: (child.classification, child.reason)
        for entry in result.entries  # pyright: ignore[reportAttributeAccessIssue]
        for child in entry.children
    }


def test_a_live_recovery_held_child_of_this_repository_is_held_and_named(tmp_path: Path) -> None:
    _write_config(tmp_path, priority=[{"repo": ".", "items": ["held", "free"]}])
    _journal(tmp_path, records=[{"at": _now(), "stage": "recovery-held", "work_item_id": "held"}])
    items = (_item(id_="held"), _item(id_="free"))

    result = _audit(tmp_path, readings={tmp_path: _reading(items=items)})

    children = _children(result)
    assert children["held"][0] == "HELD"
    assert "recovery-held" in str(children["held"][1])
    assert children["free"] == ("DISPATCHABLE-NOW", None)


def test_an_unreadable_journal_holds_this_repositorys_ready_children(tmp_path: Path) -> None:
    _write_config(tmp_path, priority=[{"repo": ".", "items": ["a", "b"]}])
    (tmp_path / "tmp" / "fabro-dispatch-journal.jsonl").mkdir(parents=True)
    items = (_item(id_="a"), _item(id_="b"))

    result = _audit(tmp_path, readings={tmp_path: _reading(items=items)})

    children = _children(result)
    assert {name: children[name][0] for name in ("a", "b")} == {"a": "HELD", "b": "HELD"}
    assert "journal cannot be read" in str(children["a"][1])


def test_another_tenants_children_are_not_held_by_this_repositorys_journal(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path, priority=[{"repo": "other", "items": ["held"]}])
    _journal(tmp_path, records=[{"at": _now(), "stage": "recovery-held", "work_item_id": "held"}])
    items = (_item(id_="held"),)

    result = _audit(tmp_path, readings={tmp_path / "other": _reading(items=items)})

    assert _children(result)["held"] == ("DISPATCHABLE-NOW", None)


def test_a_hold_the_shared_verdict_reports_keeps_its_own_reason(tmp_path: Path) -> None:
    _write_config(tmp_path, priority=[{"repo": ".", "items": ["held"]}])
    _journal(tmp_path, records=[{"at": _now(), "stage": "recovery-held", "work_item_id": "held"}])
    module = importlib.import_module(_AUDIT_NAME)

    def _verdict(*, repo: Path, items: list[WorkItem]) -> dict[str, str]:
        _ = (repo, items)
        return {"held": "manual-admission"}

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=lambda *, repo: _reading(items=(_item(id_="held"),))
        if repo == tmp_path
        else None,
        board_reader=_board(),
        hold_reader=_verdict,
    )

    assert _children(result)["held"] == ("HELD", "manual-admission")


def test_a_supplied_reading_is_applied_without_reading_the_journal_again(tmp_path: Path) -> None:
    _write_config(tmp_path, priority=[{"repo": ".", "items": ["held"]}])
    reading = importlib.import_module(_JOURNAL_NAME).JournalHoldReading(
        observable=True, holds=(), live_recovery_held_ids=frozenset({"held"})
    )

    result = _audit(
        tmp_path,
        readings={tmp_path: _reading(items=(_item(id_="held"),))},
        journal_holds=reading,
    )

    assert _children(result)["held"][0] == "HELD"


def test_the_reasons_cover_ready_rows_only() -> None:
    holds = importlib.import_module(_HOLDS_NAME)
    journal = importlib.import_module(_JOURNAL_NAME)
    items = [_item(id_="ready-held"), _item(id_="active-held", status="active"), _item(id_="free")]
    live = journal.JournalHoldReading(
        observable=True, holds=(), live_recovery_held_ids=frozenset({"ready-held", "active-held"})
    )
    blind = journal.JournalHoldReading(
        observable=False, holds=(), live_recovery_held_ids=frozenset()
    )

    assert holds.journal_hold_reasons(reading=live, items=items) == {
        "ready-held": holds.HOLD_RECOVERY_HELD
    }
    assert holds.journal_hold_reasons(reading=blind, items=items) == {
        "ready-held": holds.HOLD_JOURNAL_UNREADABLE,
        "free": holds.HOLD_JOURNAL_UNREADABLE,
    }

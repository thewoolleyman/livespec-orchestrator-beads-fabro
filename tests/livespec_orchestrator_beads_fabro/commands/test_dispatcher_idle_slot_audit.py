"""Coverage for the audit assembly across more than one tenant.

Two tenants is the minimum that makes the cross-tenant claim checkable: with
one, a reader that resolved every entry against the FIRST entry's checkout
would pass. Each injected tenant reader therefore answers per path, and the
test asserts which paths were asked.
"""

import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_PATH = _COMMANDS / "_dispatcher_idle_slot_audit.py"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit"
_TENANTS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_tenants"
_BOARD_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"
_FACTORIES = {"hp": {"server": "https://hp.example:32276"}}


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
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
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _write_config(root: Path, *, priority: list[dict[str, object]]) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": _FACTORIES,
                        "idle_slot_audit": {"factory": "hp", "priority": priority},
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _reading(*, items: tuple[WorkItem, ...]) -> object:
    records = tuple({"id": item.id, "dependencies": []} for item in items)
    return importlib.import_module(_TENANTS_NAME).TenantReading(items=items, records=records)


def _board(*, live: int = 0, queued: int = 0, live_ids: frozenset[str] = frozenset()) -> object:
    return importlib.import_module(_BOARD_NAME).BoardReading(
        observable=True, live_count=live, queued_count=queued, live_item_ids=live_ids
    )


def _classes(result: object) -> dict[str, str]:
    return {child.id: child.classification for entry in result.entries for child in entry.children}


def _no_holds(*, repo: Path, items: list[WorkItem]) -> dict[str, str]:
    _ = (repo, items)
    return {}


def _constant_board(*, board: object) -> Callable[..., object]:
    """A board reader that answers one canned reading for any factory."""

    def _read(*, repo: Path, factory: str) -> object:
        _ = (repo, factory)
        return board

    return _read


def _tenant_reader(*, readings: dict[Path, object]) -> Callable[..., object]:
    """A tenant reader that answers PER PATH, so a wrong path reads as absent."""

    def _read(*, repo: Path) -> object:
        return readings.get(repo)

    return _read


def _recorder(*, calls: list[str]) -> Callable[..., object]:
    """A reader that records the keywords it was asked with and answers nothing.

    Shared by the unreadable-tenant case, where answering nothing IS the
    subject, and by the unconfigured case, which asserts it was never asked.
    """

    def _read(**kwargs: object) -> object:
        calls.append(",".join(sorted(kwargs)))
        return None

    return _read


def test_the_audit_classifies_both_tenants_entries_against_one_board(tmp_path: Path) -> None:
    """Every entry resolves against ITS OWN checkout, and both are reported."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(
        tmp_path,
        priority=[
            {"repo": "tenant-a", "epic": "a-epic"},
            {"repo": "tenant-b", "items": ["b-1", "b-gone"]},
        ],
    )
    asked: list[Path] = []
    readings = {
        tmp_path / "tenant-a": _reading(items=(_item(id_="a-epic.1"),)),
        tmp_path / "tenant-b": _reading(items=(_item(id_="b-1", status="acceptance"),)),
    }
    per_path = _tenant_reader(readings=readings)

    def _tenant(*, repo: Path) -> object:
        asked.append(repo)
        return per_path(repo=repo)

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant,
        board_reader=_constant_board(board=_board(live=1)),
        hold_reader=_no_holds,
    )

    assert asked == [tmp_path / "tenant-a", tmp_path / "tenant-b"]
    assert result.configured is True
    assert result.factory == "hp"
    assert [entry.repo for entry in result.entries] == ["tenant-a", "tenant-b"]
    assert [child.id for child in result.entries[0].children] == ["a-epic.1"]
    assert result.entries[0].children[0].classification == "DISPATCHABLE-NOW"
    assert result.entries[1].children[0].classification == "NEEDS-CAPTURE-OR-ACCEPT"
    assert result.entries[1].missing_ids == ("b-gone",)


def test_an_unreadable_tenant_is_reported_rather_than_omitted(tmp_path: Path) -> None:
    """The entry survives with `unreadable` set; nothing about it is invented."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(tmp_path, priority=[{"repo": "tenant-a", "epic": "a-epic"}])

    asked: list[str] = []

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_recorder(calls=asked),
        board_reader=_constant_board(board=_board()),
        hold_reader=_no_holds,
    )

    assert asked == ["repo"]
    assert [entry.unreadable for entry in result.entries] == [True]
    assert result.entries[0].children == ()


def test_an_unconfigured_repository_reads_no_tenant_and_no_board(tmp_path: Path) -> None:
    """Absence is an answer: nothing is read and no finding composes."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")

    reached: list[str] = []
    recorder = _recorder(calls=reached)

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=recorder,
        board_reader=recorder,
        hold_reader=recorder,
    )

    assert reached == []

    assert (result.configured, result.configuration_finding, result.factory) == (
        False,
        None,
        None,
    )
    assert result.entries == ()


def test_a_malformed_configuration_refuses_with_its_finding(tmp_path: Path) -> None:
    """A refusal is distinguishable from an absence, because the remedies differ."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"factories": _FACTORIES, "idle_slot_audit": {"factory": "hp"}}
                }
            }
        ),
        encoding="utf-8",
    )

    result = module.idle_slot_audit(project_root=tmp_path)

    assert result.configured is False
    assert result.configuration_finding is not None
    assert "dispatcher.idle_slot_audit.priority" in result.configuration_finding


def test_the_hold_reader_runs_once_per_entry_and_only_for_a_ready_child(
    tmp_path: Path,
) -> None:
    """The shared verdict reads a whole tenant, so it is not run per row."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(
        tmp_path,
        priority=[
            {"repo": "tenant-a", "items": ["a-1", "a-2"]},
            {"repo": "tenant-b", "items": ["b-1"]},
        ],
    )
    calls: list[Path] = []

    def _holds(*, repo: Path, items: list[WorkItem]) -> dict[str, str]:
        _ = items
        calls.append(repo)
        return {"a-1": "held for a reason"}

    readings = {
        tmp_path / "tenant-a": _reading(items=(_item(id_="a-1"), _item(id_="a-2"))),
        tmp_path / "tenant-b": _reading(items=(_item(id_="b-1", status="backlog"),)),
    }
    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant_reader(readings=readings),
        board_reader=_constant_board(board=_board()),
        hold_reader=_holds,
    )

    assert calls == [tmp_path / "tenant-a"]
    assert result.entries[0].children[0].classification == "HELD"
    assert result.entries[0].children[0].reason == "held for a reason"
    assert result.entries[0].children[1].classification == "DISPATCHABLE-NOW"


def test_the_finding_names_the_factory_its_live_count_and_the_children_in_order(
    tmp_path: Path,
) -> None:
    """Configuration order, not id order: the entries are the ordering authority."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(
        tmp_path,
        priority=[
            {"repo": "tenant-b", "items": ["b-1"]},
            {"repo": "tenant-a", "items": ["a-1"]},
        ],
    )
    readings = {
        tmp_path / "tenant-b": _reading(items=(_item(id_="b-1"),)),
        tmp_path / "tenant-a": _reading(items=(_item(id_="a-1"),)),
    }

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant_reader(readings=readings),
        board_reader=_constant_board(board=_board(live=3)),
        hold_reader=_no_holds,
    )

    assert result.finding is not None
    assert result.finding.factory == "hp"
    assert result.finding.live_count == 3
    assert result.finding.child_ids == ("b-1", "a-1")
    assert result.finding.dispatchable_ids == ("b-1", "a-1")
    assert result.finding.stale_edge_ids == ()


def test_no_dispatchable_and_no_stale_edge_child_composes_no_finding(
    tmp_path: Path,
) -> None:
    """Nothing to start is not idleness — it is an empty priority queue."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(tmp_path, priority=[{"repo": "tenant-a", "items": ["a-1"]}])
    readings = {tmp_path / "tenant-a": _reading(items=(_item(id_="a-1", status="backlog"),))}

    result = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant_reader(readings=readings),
        board_reader=_constant_board(board=_board()),
        hold_reader=_no_holds,
    )

    assert result.finding is None


def test_a_runnable_row_or_an_unobservable_board_composes_no_finding(
    tmp_path: Path,
) -> None:
    """Something already waits, or nobody could look — neither is idle capacity."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(tmp_path, priority=[{"repo": "tenant-a", "items": ["a-1"]}])
    readings = {tmp_path / "tenant-a": _reading(items=(_item(id_="a-1"),))}
    unobservable = importlib.import_module(_BOARD_NAME).UNOBSERVABLE_BOARD

    queued = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant_reader(readings=readings),
        board_reader=_constant_board(board=_board(live=2, queued=1)),
        hold_reader=_no_holds,
    )
    unreadable = module.idle_slot_audit(
        project_root=tmp_path,
        tenant_reader=_tenant_reader(readings=readings),
        board_reader=_constant_board(board=unobservable),
        hold_reader=_no_holds,
    )

    assert _classes(queued)["a-1"] == "DISPATCHABLE-NOW"
    assert queued.finding is None
    assert _classes(unreadable)["a-1"] == "DISPATCHABLE-NOW"
    assert unreadable.finding is None
    assert (unreadable.board.live_count, unreadable.board.queued_count) == (None, None)

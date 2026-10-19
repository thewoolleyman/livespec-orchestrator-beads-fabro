"""Coverage for tenant reads and the two-arm child union.

The epic fixture carries one EDGE-linked child and one DOTTED-ID child
deliberately: either arm alone returns a plausible non-empty set, so a test
with only one of them passes against a half-blind union.
"""

import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_idle_slot_tenants.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_tenants"
_CONFIG_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_config"
_EPIC = "bd-epic"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _entry(*, repo: str, epic: str | None = None, items: tuple[str, ...] = ()) -> object:
    return importlib.import_module(_CONFIG_NAME).PriorityEntry(repo=repo, epic=epic, items=items)


def _reading(*, items: tuple[WorkItem, ...], records: tuple[dict[str, object], ...]) -> object:
    return _module().TenantReading(items=items, records=records)


def _constant_reader(*, reading: object) -> Callable[..., object]:
    """A tenant reader with one canned answer, including the absent answer."""

    def _read(*, repo: Path) -> object:
        _ = repo
        return reading

    return _read


def _record(*, id_: str, parent: str | None = None) -> dict[str, object]:
    dependencies = [] if parent is None else [{"depends_on_id": parent, "type": "parent-child"}]
    return {"id": id_, "dependencies": dependencies}


def test_an_epic_entry_unions_the_edge_arm_and_the_dotted_id_arm(tmp_path: Path) -> None:
    """Either arm alone omits a real child, and omits it without saying so."""
    assert _MODULE_PATH.is_file()
    module = _module()
    items = (
        _item(id_="bd-edge"),
        _item(id_=f"{_EPIC}.3"),
        _item(id_="bd-closed-edge", status="done"),
        _item(id_="bd-unrelated"),
    )
    records = (
        _record(id_="bd-edge", parent=_EPIC),
        _record(id_=f"{_EPIC}.3"),
        _record(id_="bd-closed-edge", parent=_EPIC),
        _record(id_="bd-unrelated"),
    )

    resolved = module.entry_children(
        project_root=tmp_path,
        entry=_entry(repo="tenant", epic=_EPIC),
        reader=_constant_reader(reading=_reading(items=items, records=records)),
    )

    assert [child.id for child in resolved.children] == ["bd-edge", f"{_EPIC}.3"]
    assert resolved.missing_ids == ()
    assert resolved.root == tmp_path / "tenant"


def test_an_items_entry_keeps_configuration_order_and_reports_an_absent_id(
    tmp_path: Path,
) -> None:
    """A configured id absent from its tenant is MISSING, never omitted."""
    assert _MODULE_PATH.is_file()
    module = _module()
    items = (_item(id_="bd-b"), _item(id_="bd-a"), _item(id_="bd-shut", status="done"))

    resolved = module.entry_children(
        project_root=tmp_path,
        entry=_entry(repo="tenant", items=("bd-b", "bd-gone", "bd-a", "bd-shut")),
        reader=_constant_reader(reading=_reading(items=items, records=())),
    )

    assert [child.id for child in resolved.children] == ["bd-b", "bd-a"]
    assert resolved.missing_ids == ("bd-gone",)


def test_an_unreadable_tenant_yields_no_children_and_is_reported_as_unreadable(
    tmp_path: Path,
) -> None:
    """A dropped tenant reads as a tenant with no dispatchable work."""
    assert _MODULE_PATH.is_file()
    module = _module()

    resolved = module.entry_children(
        project_root=tmp_path,
        entry=_entry(repo="tenant", epic=_EPIC),
        reader=_constant_reader(reading=None),
    )

    assert resolved.tenant is None
    assert resolved.children == ()
    assert resolved.missing_ids == ()


def test_read_tenant_reports_an_absent_checkout_and_a_failing_read_as_unreadable(
    tmp_path: Path,
) -> None:
    """Both unreadable shapes collapse to `None` without raising."""
    assert _MODULE_PATH.is_file()
    module = _module()

    def _raises(*, repo: Path) -> object:
        _ = repo
        raise BeadsConnectionError(detail="tenant unreachable")

    assert module.read_tenant(repo=tmp_path / "missing") is None
    assert module.read_tenant(repo=tmp_path, load=_raises) is None


def test_load_tenant_reads_both_shapes_through_the_tenants_own_config(
    tmp_path: Path,
) -> None:
    """One call, one resolved config: the items and the raw edges cannot desync."""
    assert _MODULE_PATH.is_file()
    module = _module()
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "tenant-under-test",
                        "prefix": "bd",
                        "server_user": "tenant-under-test",
                        "database": "tenant-under-test",
                        "bd_path": "bd",
                        "fake": True,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    append_work_item(
        path=StoreConfig(
            tenant="tenant-under-test",
            prefix="bd",
            server_user="tenant-under-test",
            database="tenant-under-test",
            bd_path="bd",
            fake=True,
        ),
        item=_item(id_="bd-seeded"),
    )

    reading = module.read_tenant(repo=tmp_path)

    assert reading is not None
    assert len(reading.items) == 1
    assert len(reading.records) == 1

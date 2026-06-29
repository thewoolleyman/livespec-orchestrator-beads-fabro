"""Tests for the close-work-item atomic close + resolution:completed wrapper.

The hermetic `FakeBeadsClient` is the backend (the autouse conftest sets
`LIVESPEC_BEADS_FAKE=1` and resets the singleton). Work-items are seeded
into the same in-memory tenant the wrapper reads/writes by calling
`append_work_item` with a `fake=True` descriptor; the process-singleton
fake makes the seeded writes visible.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands.close_work_item import close_completed, main
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _open_item(
    *,
    id_: str,
    origin: str = "gap-tied",
    gap_id: str | None = "gap-j2femmn7",
    reason: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="feature",  # type: ignore[arg-type]
        status="ready",
        title="t",
        description="d",
        origin=origin,  # type: ignore[arg-type]
        gap_id=gap_id,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-20T00:00:00Z",
        resolution=None,
        reason=reason,
        audit=None,
        superseded_by=None,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _reload(item_id: str) -> WorkItem | None:
    return materialize_work_items(records=read_work_items(path=_config())).get(item_id)


# --------------------------------------------------------------------------
# close_completed — the load-bearing seam.
# --------------------------------------------------------------------------


def test_close_completed_sets_closed_and_resolution() -> None:
    _seed(_open_item(id_="li-x"))
    closed = close_completed(path=_config(), item_id="li-x", reason="done")
    assert closed.status == "done"
    assert closed.resolution == "completed"
    assert closed.reason == "done"


def test_close_completed_persists_resolution_label() -> None:
    """The reloaded item carries status closed AND resolution completed — the
    label and the close land in the same operation (the pit of success)."""
    _seed(_open_item(id_="li-x"))
    _ = close_completed(path=_config(), item_id="li-x", reason="done")
    reloaded = _reload("li-x")
    assert reloaded is not None
    assert reloaded.status == "done"
    assert reloaded.resolution == "completed"


def test_close_completed_falls_back_to_existing_reason() -> None:
    """When no reason is supplied, the item's existing (round-tripped) close
    reason is preserved. An open item carries no persisted close_reason, so
    the fallback is exercised against an already-closed item whose reason the
    store round-trips through `close_reason`."""
    _seed(_open_item(id_="li-x"))
    _ = close_completed(path=_config(), item_id="li-x", reason="first-close")
    # Re-close with no reason: the prior close_reason is preserved.
    closed = close_completed(path=_config(), item_id="li-x")
    assert closed.reason == "first-close"
    assert closed.resolution == "completed"


def test_close_completed_missing_id_raises() -> None:
    with pytest.raises(WorkItemNotFoundError) as excinfo:
        _ = close_completed(path=_config(), item_id="li-absent", reason="x")
    assert excinfo.value.item_id == "li-absent"


# --------------------------------------------------------------------------
# main — the thin CLI surface.
# --------------------------------------------------------------------------


def test_main_closes_and_reports(capsys: pytest.CaptureFixture[str]) -> None:
    _seed(_open_item(id_="li-x"))
    code = main(["li-x", "--reason", "shipped"])
    assert code == 0
    out = capsys.readouterr().out
    assert "closed li-x resolution:completed" in out
    reloaded = _reload("li-x")
    assert reloaded is not None
    assert reloaded.resolution == "completed"


def test_main_missing_id_exits_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["li-absent"])
    assert code == 3
    err = capsys.readouterr().err
    assert "work-item not found" in err


def test_main_uses_cwd_project_root_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no --project-root, the wrapper resolves the store from cwd."""
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    # The wrapper resolves the tenant connection from cwd via
    # resolve_store_config, which REQUIRES an explicit connection.prefix
    # (decoupled from the tenant DB name); mirror a real governed repo.
    _ = (tmp_path / ".livespec.jsonc").write_text(  # type: ignore[attr-defined]
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _seed(_open_item(id_="li-x"))
    code = main(["li-x"])
    assert code == 0
    assert "closed li-x" in capsys.readouterr().out

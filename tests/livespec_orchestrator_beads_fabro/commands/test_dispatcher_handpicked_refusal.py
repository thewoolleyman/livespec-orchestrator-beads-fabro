"""Tests for the early hand-picked factory-safety refusal."""

from __future__ import annotations

import importlib
from argparse import Namespace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_handpicked_refusal.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_handpicked_refusal"


def _item(*, item_id: str, factory_safety: str | None = None) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="A ready task",
        description="## Definition of Done\n\n- The change lands.\n\nReferences: ## Example",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        factory_safety=factory_safety,
    )


def _module() -> object:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_no_item_selection_skips_the_handpicked_refusal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "load_items", lambda **_kwargs: pytest.fail("unexpected read"))

    assert (
        module.handpicked_host_only_refusal_exit(args=Namespace(items=None), repo=tmp_path) is None
    )


def test_ordinary_and_unrequested_items_are_not_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _module()
    ordinary = _item(item_id="bd-ib-ordinary")
    monkeypatch.setattr(
        module,
        "load_items",
        lambda **_kwargs: [_item(item_id="bd-ib-other", factory_safety="host"), ordinary],
    )
    monkeypatch.setattr(module, "read_dispatch_labels", lambda **_kwargs: ())

    assert (
        module.handpicked_host_only_refusal_exit(args=Namespace(items=[ordinary.id]), repo=tmp_path)
        is None
    )


def test_host_only_item_refuses_once_before_dispatch_preparation(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _module()
    item = _item(item_id="bd-ib-host", factory_safety="host-machinery")
    monkeypatch.setattr(module, "load_items", lambda **_kwargs: [item])
    monkeypatch.setattr(module, "read_dispatch_labels", lambda **_kwargs: ())

    assert (
        module.handpicked_host_only_refusal_exit(args=Namespace(items=[item.id]), repo=tmp_path)
        == 5
    )
    assert capsys.readouterr().err.splitlines() == [
        "REFUSED: work-item bd-ib-host is host-only; no claim was taken and no factory run was created."
    ]

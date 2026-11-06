"""Admission changes a claim only through the enabled token protocol."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-admission-token",
        type="task",
        status="ready",
        title="Admit only after winning its current claim token",
        description="Exercise the Dispatcher admission writer.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_enabled_admission_writes_active_and_fabro_through_claim_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The active transition is the token winner's one item write."""
    admission = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_admission"
    )
    item = _item()
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(admission, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(admission, "rework_pending_candidates", lambda **_: ())
    monkeypatch.setattr(
        admission, "filter_eligible_candidates", lambda *, candidates, **_: (list(candidates), [])
    )
    monkeypatch.setattr(
        admission, "admit_rework", lambda **_: SimpleNamespace(admitted=(), deferred=())
    )
    monkeypatch.setattr(
        admission,
        "plan_admissions",
        lambda **_: SimpleNamespace(approved=(), admitted=((item, "fabro"),), held=()),
    )
    monkeypatch.setattr(admission, "store_config", lambda **_: object())
    monkeypatch.setattr(admission, "make_beads_client", lambda **_: object(), raising=False)
    monkeypatch.setattr(admission, "stamp_pending_claim", lambda **_: None)
    monkeypatch.setattr(admission, "write_dispatch_lock", lambda **_: None)
    monkeypatch.setattr(
        admission, "update_work_item_status", lambda **_: pytest.fail("blind write")
    )
    monkeypatch.setattr(
        admission,
        "change_claim",
        lambda **kwargs: writes.append(kwargs) or SimpleNamespace(outcome="applied"),
        raising=False,
    )
    monkeypatch.setattr(admission, "claim_tokens_enabled", lambda **_: True, raising=False)

    result = admission.admit_and_select(
        repo=tmp_path,
        items=[item],
        candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        enforce_cap=False,
    )

    assert [admitted.id for admitted in result.admitted] == [item.id]
    assert len(writes) == 1
    assert writes[0]["work_item_id"] == item.id
    assert writes[0]["writer"] == "dispatcher-admission"
    assert writes[0]["intent"] == "admit"
    assert writes[0]["claim_tokens"] is True
    assert writes[0]["status"] == "active"
    assert writes[0]["assignee"] == "fabro"

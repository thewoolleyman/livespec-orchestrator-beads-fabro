"""The absent-run release writes its capture receipt after the state transition."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery"
_ITEM_ID = "bd-ib-receiptorder"
_RUN_ID = "01RECEIPTORDERRUN"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
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
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice whose run vanished",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base)


def test_the_receipt_is_written_after_the_release_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    item = _item()
    append_work_item(path=_config(), item=item)
    record_claim_stamp(
        path=_config(),
        work_item_id=item.id,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="owning-host",
            run_id=_RUN_ID,
            factory_name="hp",
            factory_server="https://hp.example:32276",
        ),
    )
    journal_path = repo / "tmp" / "journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _ = journal_path.write_text("", encoding="utf-8")
    module = importlib.import_module(_MODULE_NAME)
    statuses: list[str] = []

    def _observe(**_kwargs: object) -> None:
        statuses.append(next(iter(read_work_items(path=_config()))).status)

    monkeypatch.setattr(module, "record_wip_capture_receipt", _observe)

    outcome = module.recover_claim(
        repo=repo,
        journal=JournalFile(path=journal_path),
        request=module.ClaimRecoveryRequest(
            item=item,
            run_id=_RUN_ID,
            factory_name="hp",
            factory_server_url="https://hp.example:32276",
            action="absent-run-release",
            predecessor_run_id="01PREVIOUSRUN",
        ),
        now_iso="2026-10-18T09:00:00Z",
    )

    assert module.EFFECT_TRANSITION in outcome.effects_written
    assert statuses == [next(iter(read_work_items(path=_config()))).status]
    assert statuses != ["active"]

"""The WIP-capture receipt never sits in front of the transition it must not delay."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_selection as loop_selection,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_recovery as recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-ordering"
_RUN_ID = "01ORDERINGRUN"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice",
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


def _status() -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    path: Path | None = None

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_release_receipt_is_written_after_the_item_leaves_active(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
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
    seen: list[str] = []

    def _spy(**_kwargs: object) -> None:
        seen.append(_status())

    monkeypatch.setattr(recovery, "record_wip_capture_receipt", _spy)

    outcome = recovery.recover_claim(
        repo=repo,
        journal=JournalFile(path=journal_path),
        request=recovery.ClaimRecoveryRequest(
            item=item,
            run_id=_RUN_ID,
            factory_name="hp",
            factory_server_url="https://hp.example:32276",
            action="absent-run-release",
            predecessor_run_id="01PREVIOUSRUN",
        ),
        now_iso="2026-10-18T09:00:00Z",
    )

    assert isinstance(outcome, recovery.RecoveredClaim)
    assert seen == ["ready"]


def test_post_run_receipt_is_written_after_the_blocked_transition(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib",'
        ' "tenant": "livespec-impl-beads", "server_user": "livespec-impl-beads",'
        ' "database": "livespec-impl-beads", "bd_path": "bd", "fake": true}}}',
        encoding="utf-8",
    )
    item = replace(_item(), status="active")
    append_work_item(path=_config(), item=item)
    seen: list[str] = []

    def _spy(**_kwargs: object) -> None:
        seen.append(_status())

    monkeypatch.setattr(loop_selection, "record_wip_capture_receipt", _spy)
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run parked at the in-loop human gate (needs-human)",
        fabro_run_id=_RUN_ID,
    )

    loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=item,
        outcome=outcome,
        journal=_Journal(),
        wall_clock_seconds=1.0,
        dispatch_context_size=100,
        token_supplier=lambda: "token",
    )

    assert seen == ["blocked"]

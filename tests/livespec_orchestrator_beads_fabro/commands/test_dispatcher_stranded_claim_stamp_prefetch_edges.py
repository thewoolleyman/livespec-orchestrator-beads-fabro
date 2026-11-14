"""The edges of the survey's batched claim-stamp read.

`test_dispatcher_stranded_claim_stamp_batch.py` binds the one multi-id `show`. These are the
readings that journey cannot reach: the store's batch answering stamped, unstamped and
absent ids apart, a batch the ledger could not answer, and a claim the batch did not name.
Each of the last two falls back to the single-row read, so a ledger fault is still
reported as the unreadable stamp it always was and never as a claim with no stamp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_stamps_for,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_population as module,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_STAMPED = "bd-ib-prefetchstamped"
_BARE = "bd-ib-prefetchbare"
_BACKLOG = "bd-ib-prefetchbacklog"
_STAMP = ClaimStamp(
    dispatch_id="01DISPATCH",
    dispatching_host="owning-host",
    run_id="01RUN",
    factory_name="hp",
    factory_server="https://hp.example:32276",
)


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


def _item(*, item_id: str, status: Literal["active", "backlog"]) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status=status,
        title="A claim",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _seed() -> tuple[WorkItem, ...]:
    items = (
        _item(item_id=_STAMPED, status="active"),
        _item(item_id=_BARE, status="active"),
        _item(item_id=_BACKLOG, status="backlog"),
    )
    for item in items:
        append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=_STAMPED, stamp=_STAMP)
    record_claim_stamp(path=_config(), work_item_id=_BACKLOG, stamp=_STAMP)
    return items


def test_the_batch_names_a_stamp_a_bare_row_and_leaves_an_absent_id_out() -> None:
    _ = _seed()

    stamps = claim_stamps_for(path=_config(), work_item_ids=[_STAMPED, _BARE, "bd-ib-nothere"])

    assert stamps == {_STAMPED: _STAMP, _BARE: None}


def test_a_batch_the_ledger_could_not_answer_falls_back_to_the_single_row_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = _seed()

    def refuse(**_kwargs: object) -> dict[str, ClaimStamp | None]:
        raise BeadsCommandError(command="show", exit_code=1, stderr="refused")

    monkeypatch.setattr(module, "claim_stamps_for", refuse)
    stamp_of = module.prefetched_claim_stamps(repo=_repo(tmp_path=tmp_path), items=items)

    assert stamp_of(work_item_id=_STAMPED) == _STAMP


def test_a_claim_the_batch_did_not_name_is_read_on_its_own(tmp_path: Path) -> None:
    items = _seed()
    stamp_of = module.prefetched_claim_stamps(repo=_repo(tmp_path=tmp_path), items=items)

    assert stamp_of(work_item_id=_BACKLOG) == _STAMP

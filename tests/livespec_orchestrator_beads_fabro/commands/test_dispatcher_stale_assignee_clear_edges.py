"""The refusals a stale-assignee clearance reaches only under a fault or a race.

The clearance holds under a lock and re-reads the item before writing. These
cases drive `clear_stale_assignee` directly for the arms the survey cannot reach
from a healthy tenant: a lock that cannot be taken, an item that moved between
the survey's grading and the clearance, an unreadable row, and a comment that
cannot be established. Each must write nothing further and name its reason.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_STAMP_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands import _dispatcher_stale_assignee_clear as clear
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-staleedge"
_RUN_ID = "01M4VSTCF4GW0000000000000C"


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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A ready item still assigned fabro",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _seed(*, item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    raw = client.show_issue(issue_id=item.id).get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata[CLAIM_STAMP_METADATA_KEY] = {
        "dispatch_id": "01DISPATCHONE",
        "dispatching_host": "test-dispatching-host",
        "run_id": _RUN_ID,
        "factory": {"name": "hp", "server": "https://hp.example:32276"},
    }
    client.update_issue(issue_id=item.id, metadata=metadata)


def _request(*, item: WorkItem) -> Any:
    return clear.StaleClearRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        run_state="failed",
    )


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps({"stage": "dispatch-id"}) + "\n", encoding="utf-8")
    return JournalFile(path=path)


def _clear(*, repo: Path, item: WorkItem) -> Any:
    return clear.clear_stale_assignee(
        repo=repo, journal=_journal(repo=repo), request=_request(item=item)
    )


def _stored() -> WorkItem:
    return next(iter(read_work_items(path=_config())))


def test_a_lock_that_cannot_be_taken_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)

    @contextmanager
    def _no_lock(**_: object) -> Iterator[bool]:
        yield False

    monkeypatch.setattr(clear, "claim_recovery_fence", _no_lock)

    held = _clear(repo=repo, item=item)

    assert held.hold_reason == "effect-unobservable"
    assert _stored().assignee == "fabro"
    assert not read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)


def test_an_item_that_moved_before_the_clearance_began_is_held_claim_changed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    make_beads_client(config=_config()).update_issue(issue_id=_ITEM_ID, status="backlog")

    held = _clear(repo=repo, item=item)

    assert held.hold_reason == "claim-changed"
    assert (_stored().status, _stored().assignee) == ("backlog", "fabro")
    assert not read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)


def test_an_unreadable_row_is_held_effect_unobservable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    monkeypatch.setattr(clear, "claim_row", lambda **_: None)

    held = _clear(repo=repo, item=item)

    assert held.hold_reason == "effect-unobservable"
    assert _stored().assignee == "fabro"


def test_a_comment_that_cannot_be_established_is_held_and_the_assignee_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    monkeypatch.setattr(clear, "establish_comment", lambda **_: None)

    held = _clear(repo=repo, item=item)

    assert held.hold_reason == "effect-unobservable"
    assert _stored().assignee == "fabro"

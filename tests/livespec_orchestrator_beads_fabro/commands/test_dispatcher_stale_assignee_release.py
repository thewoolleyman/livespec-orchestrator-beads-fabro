"""A stale assignee is released for recovery, cleared or not.

`contracts.md` "Recovery from the failed run's preserved work": an item is
released for recovery when a `stale-assignee-clear` record ends its latest
dispatch, and "while it is a stale assignee whose run stamp names a run". The
second half is what keeps a HELD stale assignee released: it has no clear row,
and its next dispatch must still be graded by recovery routing rather than
routed fresh on top of an open pull request.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_STAMP_METADATA_KEY
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    RELEASE_STAGES,
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import ROUTE_FRESH
from livespec_orchestrator_beads_fabro.commands._dispatcher_stale_assignee_release import (
    stale_assignee_with_run,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-stalerel"
_RUN_ID = "01M58N2ATX8N0000000000000A"


class _ReachedError(Exception):
    """Raised by the stand-in for the resume measurement, which only a released item reaches."""


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


def _seed(*, item: WorkItem, stamp: dict[str, Any] | None) -> None:
    append_work_item(path=_config(), item=item)
    if stamp is None:
        return
    client = make_beads_client(config=_config())
    raw = client.show_issue(issue_id=item.id).get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata[CLAIM_STAMP_METADATA_KEY] = stamp
    client.update_issue(issue_id=item.id, metadata=metadata)


def _run_stamp() -> dict[str, Any]:
    return {
        "dispatch_id": "01DISPATCHONE",
        "dispatching_host": "test-dispatching-host",
        "run_id": _RUN_ID,
        "factory": {"name": "hp", "server": "https://hp.example:32276"},
    }


def _pending_stamp() -> dict[str, Any]:
    return {key: value for key, value in _run_stamp().items() if key != "run_id"}


def test_a_stale_assignee_clear_record_is_a_recovery_release() -> None:
    assert "stale-assignee-clear" in RELEASE_STAGES
    records = [
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
        {"stage": "stale-assignee-clear", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
    ]

    assert released_for_recovery(records=records, work_item_id=_ITEM_ID)
    assert not released_for_recovery(
        records=[*records, {"stage": "dispatch-id", "work_item_id": _ITEM_ID}],
        work_item_id=_ITEM_ID,
    )


@pytest.mark.parametrize(
    ("item", "stamp", "expected"),
    [
        (_item(), _run_stamp(), True),
        (_item(), _pending_stamp(), False),
        (_item(), None, False),
        (_item(assignee=None), _run_stamp(), False),
        (_item(status="active"), _run_stamp(), False),
    ],
)
def test_only_a_ready_fabro_item_stamped_with_a_run_is_a_stale_assignee_with_a_run(
    tmp_path: Path, item: WorkItem, stamp: dict[str, Any] | None, *, expected: bool
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=item, stamp=stamp)

    assert stale_assignee_with_run(repo=repo, item=item) is expected


def test_an_unreadable_row_is_not_a_stale_assignee_with_a_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)

    assert not stale_assignee_with_run(repo=repo, item=_item())


@pytest.mark.parametrize(
    ("stamp", "reaches_measurement"),
    [(_run_stamp(), True), (_pending_stamp(), False)],
)
def test_recovery_routing_grades_a_held_stale_assignee_as_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stamp: dict[str, Any],
    *,
    reaches_measurement: bool,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=stamp)
    journal_path = repo / "tmp" / "journal.jsonl"
    journal_path.parent.mkdir(parents=True)
    _ = journal_path.write_text(
        json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID}) + "\n", encoding="utf-8"
    )

    def _measure(**_: object) -> object:
        raise _ReachedError

    monkeypatch.setattr(routing, "gather_resume", _measure)
    args = argparse.Namespace()
    journal = JournalFile(path=journal_path)

    if reaches_measurement:
        with pytest.raises(_ReachedError):
            _ = routing.route_recovery(args=args, repo=repo, candidates=[item], journal=journal)
        return
    routed = routing.route_recovery(args=args, repo=repo, candidates=[item], journal=journal)
    assert [one.route for one in routed.routes] == [ROUTE_FRESH]

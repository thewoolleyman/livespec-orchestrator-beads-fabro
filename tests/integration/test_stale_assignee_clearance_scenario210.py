"""Scenario 210 — a reconcile-runs pass clears a stale fabro assignee from a ready item.

`SPECIFICATION/contracts.md` section "Stranded claim release" → "Stale assignee
clearance". A work-item resting at `ready` with the `fabro` assignee still on it
is not a dispatch claim, yet an ownership sweep that filters on status reads it
as available and an assignee sweep reads it as owned. The pass clears the
assignee when the item's own run stamp names this host and the factory reports
the run terminal or absent with no live owner, and holds with a named reason
otherwise; either way the item stays released for recovery, so its next dispatch
is graded by recovery routing rather than started fresh.

Integration tier: the real `reconcile_runs` pass runs over the in-memory ledger,
the real claim lane is injected as the two reconciliation surfaces inject it, and
the only stand-ins are the `fabro ps` / `gh` shell seam and the host name.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_claim_lane import (
    reconcile_claim_lane,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-staleint"
_RUN_ID = "01M58N2ATX8N0000000000000B"
_HOST = "owning-host"
_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
_CLEAR_STAGE = "stale-assignee-clear"


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


def _stamp(**overrides: object) -> ClaimStamp:
    base = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )
    return replace(base, **overrides)


def _seed(*, stamp: ClaimStamp) -> WorkItem:
    item = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A ready item whose last run is terminal",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=item.id, stamp=stamp)
    return item


class _Runner:
    """A fake `fabro ps` seam answering one scripted run listing."""

    def __init__(self, *, listing: list[dict[str, Any]]) -> None:
        self.listing = listing

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout=json.dumps(self.listing), stderr="")


def _run_row(*, kind: str) -> dict[str, Any]:
    return {
        "run_id": _RUN_ID,
        "goal": f"Work-item: {_ITEM_ID}\nRepo: /tmp/repo",
        "status": {"kind": kind},
    }


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = (
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
        {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
    )
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _pass(
    *, repo: Path, journal: JournalFile, listing: list[dict[str, Any]], dry_run: bool = False
) -> Any:
    return reconcile.reconcile_runs(
        inputs=ReconcileInputs(
            repo=repo,
            fabro_bin="fabro",
            id_prefix="bd-ib",
            items=list(read_work_items(path=_config())),
            journaled=journaled_runs(text=""),
            runner=_Runner(listing=listing),
            journal=journal,
            ledger=make_beads_client(config=_config()),
            blocked_run_grace_seconds=0,
            claim_journal=journal,
            claim_host=_HOST,
            claim_lane=reconcile_claim_lane,
        ),
        factories=[_HP],
        dry_run=dry_run,
    )


def _records(*, journal: JournalFile) -> list[dict[str, Any]]:
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _only_item() -> WorkItem:
    return next(iter(read_work_items(path=_config())))


@pytest.mark.parametrize(
    ("listing", "state"),
    [
        ([_run_row(kind="failed")], "failed"),
        ([], "absent"),
        ([_run_row(kind="succeeded")], "succeeded"),
    ],
)
def test_a_pass_clears_a_stale_assignee_and_leaves_the_item_released_for_recovery(
    tmp_path: Path, listing: list[dict[str, Any]], state: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _seed(stamp=_stamp())
    journal = _journal(repo=repo)

    summary = _pass(repo=repo, journal=journal, listing=listing)

    cleared = _only_item()
    assert (cleared.status, cleared.assignee) == ("ready", None)
    assert [(one.route, one.reason) for one in summary.recovered_claims] == [(_CLEAR_STAGE, state)]
    assert summary.held_claims == ()
    rows = [row for row in _records(journal=journal) if row.get("stage") == _CLEAR_STAGE]
    assert [(row["work_item_id"], row["run_id"], row["run_state"]) for row in rows] == [
        (_ITEM_ID, _RUN_ID, state)
    ]
    assert len(read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)) == 1
    assert released_for_recovery(records=_records(journal=journal), work_item_id=_ITEM_ID)


def test_a_second_pass_over_a_cleared_stale_assignee_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _seed(stamp=_stamp())
    journal = _journal(repo=repo)
    _ = _pass(repo=repo, journal=journal, listing=[_run_row(kind="failed")])

    second = _pass(repo=repo, journal=journal, listing=[_run_row(kind="failed")])

    assert (second.recovered_claims, second.held_claims) == ((), ())
    rows = [row for row in _records(journal=journal) if row.get("stage") == _CLEAR_STAGE]
    assert len(rows) == 1
    assert len(read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)) == 1


@pytest.mark.parametrize(
    ("stamp", "reason"),
    [
        (_stamp(dispatching_host="another-host"), "owner-elsewhere"),
        (_stamp(run_id=None), "attribution-pending"),
    ],
)
def test_a_pass_holds_a_stale_assignee_it_cannot_attribute_and_changes_nothing(
    tmp_path: Path, stamp: ClaimStamp, reason: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _seed(stamp=stamp)
    journal = _journal(repo=repo)

    summary = _pass(repo=repo, journal=journal, listing=[_run_row(kind="failed")])

    held = _only_item()
    assert (held.status, held.assignee) == ("ready", "fabro")
    assert [one.hold_reason for one in summary.held_claims] == [reason]
    assert summary.recovered_claims == ()
    assert not read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)


def test_a_pass_holds_a_stale_assignee_whose_run_the_factory_reports_running(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _seed(stamp=_stamp())
    journal = _journal(repo=repo)

    summary = _pass(repo=repo, journal=journal, listing=[_run_row(kind="running")])

    assert _only_item().assignee == "fabro"
    assert [one.hold_reason for one in summary.held_claims] == ["run-live"]

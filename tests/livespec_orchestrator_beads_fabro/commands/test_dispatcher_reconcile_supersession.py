"""Tests for re-confirming a supersession against evidence as new as the run.

The module import is deferred into each test body via `importlib`, and the
first assertion is a genuine check on the module PATH, so this file reports a
missing module as a failed assertion rather than as a collection error.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    ORPHAN_REASON_SUPERSEDED_RUN,
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_supersession"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_reconcile_supersession.py"
)

_HP_SERVER = "https://hp.example:32276"
_HP_DEV_TOKEN_VALUE = "hp-fixture-dev-token"
_HP = FactoryTarget(name="hp", server=_HP_SERVER, dev_token=_HP_DEV_TOKEN_VALUE)
_ITEM_ID = "bd-ib-super"
_FIRST_RUN = "01FIRST"
_SECOND_RUN = "01SECOND"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI; every verb other than `ps` succeeds silently."""

    ps_rows: str = "[]"
    calls: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv[1])
        if argv[1] == "ps":
            return CommandResult(exit_code=0, stdout=self.ps_rows, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    """A transport that records every route, so a cancel cannot go unnoticed."""

    calls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (headers, body, timeout_seconds)
        self.calls.append(f"{method} {url}")
        return FabroHttpResult(status=200, body="{}", error=None, payload=None, succeeded=True)


@dataclass(kw_only=True)
class _Journal:
    written: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.written.append(record)


@dataclass(kw_only=True)
class _Ledger:
    """A comments-only ledger fake that genuinely stores what it is handed."""

    comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        return list(self.comments.get(issue_id, []))

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.comments.setdefault(issue_id, []).append({"id": f"c-{issue_id}", "text": body})


def test_a_genuinely_superseded_run_is_confirmed_against_a_fresh_read(tmp_path: Path) -> None:
    """A run the fresh journal read does NOT name as newest is still superseded."""
    module = _import()
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN, _SECOND_RUN])

    confirmation = module.confirm_supersession(
        orphan=_orphan(run_id=_FIRST_RUN),
        journaled=read_journaled_runs(path=journal),
    )

    assert (confirmation.hold_reason, confirmation.newest_run_id) == (None, _SECOND_RUN)


def test_a_genuinely_superseded_run_is_still_cancelled(tmp_path: Path) -> None:
    """The arm the race repair narrows keeps acting on a real supersession."""
    assert _MODULE_PATH.is_file(), f"the supersession module does not exist: {_MODULE_PATH}"
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN, _SECOND_RUN])
    runner = _Runner(ps_rows=_ps(run_id=_FIRST_RUN))
    transport = _Transport()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            journal_path=journal,
            runner=runner,
            transport=transport,
        ),
        factories=[_HP],
    )

    assert [(run.run_id, run.orphan_reason) for run in summary.reconciled] == [
        (_FIRST_RUN, ORPHAN_REASON_SUPERSEDED_RUN)
    ]
    assert f"POST {_HP_SERVER}/api/v1/runs/{_FIRST_RUN}/cancel" in transport.calls


def _import() -> Any:
    assert _MODULE_PATH.is_file(), f"the supersession module does not exist: {_MODULE_PATH}"
    return importlib.import_module(_MODULE)


def _stamped(*, tmp_path: Path, run_ids: list[str]) -> Path:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    _append_stamps(path=path, run_ids=run_ids)
    return path


def _append_stamps(*, path: Path, run_ids: list[str]) -> None:
    lines = [
        json.dumps({"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": run_id})
        for run_id in run_ids
    ]
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write("".join(f"{line}\n" for line in lines))


def _inputs(
    *,
    tmp_path: Path,
    journal_path: Path,
    runner: _Runner,
    transport: _Transport,
    journal: _Journal | None = None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=[_item(status="active")],
        journaled=read_journaled_runs(path=journal_path),
        runner=runner,
        journal=_Journal() if journal is None else journal,
        ledger=_Ledger(),
        attribution=RunAttribution(metadata_run_ids={_SECOND_RUN: _ITEM_ID}),
        http=transport,
        blocked_run_grace_seconds=0,
    )


def _orphan(*, run_id: str, reason: str = ORPHAN_REASON_SUPERSEDED_RUN) -> OrphanRun:
    return OrphanRun(
        run_id=run_id,
        factory_name="hp",
        factory_server_url=_HP_SERVER,
        status_kind="running",
        work_item_id=_ITEM_ID,
        work_item_status="active",
        orphan_reason=reason,
        tenant="bd-ib",
    )


def _ps(*, run_id: str) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": f"Work-item: {_ITEM_ID}\nRepo: /tmp/repo",
                "status": {"kind": "running"},
            }
        ]
    )


def _item(*, status: str) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        blocked_reason=None,
        title=_ITEM_ID,
        description=_ITEM_ID,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )

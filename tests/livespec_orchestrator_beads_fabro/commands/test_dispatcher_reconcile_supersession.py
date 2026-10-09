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
    ORPHAN_REASON_ITEM_NOT_ACTIVE,
    ORPHAN_REASON_SUPERSEDED_RUN,
    JournaledRuns,
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    BLOCKED_HOLD_UNMEASURED,
    BLOCKED_HOLD_WITHIN_GRACE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_supersession"
_RECORDS_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records"
# The stage the sweep writes for a run it declines to cancel. Spelled out here
# rather than imported so a missing constant is a failed assertion rather than
# a collection error.
_HOLD_STAGE = "orphan-run-reconcile-held"
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
_QUESTIONS_PATH = f"/api/v1/runs/{_SECOND_RUN}/questions"
_ANSWER_PATH = f"{_QUESTIONS_PATH}/q-abandon/answer"
_CANCEL_PATH = f"/api/v1/runs/{_SECOND_RUN}/cancel"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI; every verb other than `ps` succeeds silently."""

    ps_rows: str = "[]"
    stamp_on_dump: tuple[Path, str] | None = None
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
        if argv[1] == "dump" and self.stamp_on_dump is not None:
            path, run_id = self.stamp_on_dump
            _append_stamps(path=path, run_ids=[run_id])
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    """A transport that records every route, so a cancel cannot go unnoticed."""

    response_bodies: dict[tuple[str, str], str] = field(default_factory=dict)
    failed_routes: set[tuple[str, str]] = field(default_factory=set)
    stamp_on_route: tuple[str, str, Path, str] | None = None
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
        path = url.removeprefix(_HP_SERVER)
        route = (method, path)
        if self.stamp_on_route is not None:
            stamp_method, stamp_path, journal_path, run_id = self.stamp_on_route
            if route == (stamp_method, stamp_path):
                _append_stamps(path=journal_path, run_ids=[run_id])
        if route in self.failed_routes:
            return FabroHttpResult(
                status=500,
                body="",
                error=None,
                payload=None,
                succeeded=False,
            )
        return FabroHttpResult(
            status=200,
            body=self.response_bodies.get(route, "{}"),
            error=None,
            payload=None,
            succeeded=True,
        )


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


def test_a_run_stamped_after_the_snapshot_is_not_cancelled(tmp_path: Path) -> None:
    """The measured race: a sibling session's stamp lands after the snapshot read.

    The inventory run is the NEWEST dispatch for the item, but the pass is
    holding the previous dispatch's run id, so the stale join reads it as
    `superseded-run`. Cancelling it destroyed live work on 2026-10-09.
    """
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    runner = _Runner(ps_rows=_ps(run_id=_SECOND_RUN))
    transport = _Transport()
    inputs = _inputs(
        tmp_path=tmp_path,
        journal_path=journal,
        runner=runner,
        transport=transport,
    )
    # The sibling session stamps ITS dispatch after this pass took its snapshot.
    _append_stamps(path=journal, run_ids=[_SECOND_RUN])
    assert inputs.journaled.newest_run_id_by_item == {_ITEM_ID: _FIRST_RUN}

    summary = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert summary.reconciled == ()
    assert transport.calls == []
    # Nothing was exported and nothing was destroyed: the run never reached the
    # termination path at all.
    assert runner.calls == ["ps"]


def test_a_run_stamped_during_export_is_rechecked_at_the_cancel_boundary(
    tmp_path: Path,
) -> None:
    """A stamp landing during `dump` invalidates the earlier supersession reading.

    Export and ledger read-back intentionally precede termination.  The final
    journal read therefore belongs after them: a read before `dump` cannot
    authorize the later cancel when another dispatch stamps this run while the
    export is in flight.
    """
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    runner = _Runner(
        ps_rows=_ps(run_id=_SECOND_RUN),
        stamp_on_dump=(journal, _SECOND_RUN),
    )
    transport = _Transport()
    journal_writer = _Journal()
    ledger = _Ledger()
    inputs = _inputs(
        tmp_path=tmp_path,
        journal_path=journal,
        runner=runner,
        transport=transport,
        journal=journal_writer,
        ledger=ledger,
    )

    summary = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert summary.reconciled == ()
    assert transport.calls == []
    assert runner.calls == ["ps", "dump"]
    assert len(ledger.comments[_ITEM_ID]) == 1
    assert [row["stage"] for row in journal_writer.written] == [_HOLD_STAGE]


def test_a_run_stamped_during_question_discovery_is_held_before_answer(
    tmp_path: Path,
) -> None:
    """Non-destructive route preparation cannot authorize a later answer."""
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    runner = _Runner(ps_rows=_ps(run_id=_SECOND_RUN, status_kind="blocked"))
    transport = _Transport(
        response_bodies={
            ("GET", _QUESTIONS_PATH): json.dumps(
                {
                    "data": [
                        {
                            "id": "q-abandon",
                            "options": [{"key": "A", "label": "Abandon this run"}],
                        }
                    ]
                }
            )
        },
        stamp_on_route=("GET", _QUESTIONS_PATH, journal, _SECOND_RUN),
    )
    journal_writer = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            journal_path=journal,
            runner=runner,
            transport=transport,
            journal=journal_writer,
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert transport.calls == [f"GET {_HP_SERVER}{_QUESTIONS_PATH}"]
    assert f"POST {_HP_SERVER}{_ANSWER_PATH}" not in transport.calls
    assert f"POST {_HP_SERVER}{_CANCEL_PATH}" not in transport.calls
    assert runner.calls == ["ps", "dump"]
    assert [row["stage"] for row in journal_writer.written] == [_HOLD_STAGE]


def test_a_run_stamped_during_failed_cancel_is_held_before_rm_force(
    tmp_path: Path,
) -> None:
    """A failed cancel cannot authorize a later destructive CLI fallback."""
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    runner = _Runner(ps_rows=_ps(run_id=_SECOND_RUN))
    transport = _Transport(
        failed_routes={("POST", _CANCEL_PATH)},
        stamp_on_route=("POST", _CANCEL_PATH, journal, _SECOND_RUN),
    )
    journal_writer = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            journal_path=journal,
            runner=runner,
            transport=transport,
            journal=journal_writer,
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert transport.calls == [f"POST {_HP_SERVER}{_CANCEL_PATH}"]
    assert runner.calls == ["ps", "dump"]
    assert [row["stage"] for row in journal_writer.written] == [_HOLD_STAGE]


def test_a_snapshot_that_cannot_be_re_read_holds_rather_than_cancelling(tmp_path: Path) -> None:
    """A snapshot naming no source cannot be re-taken, so the arm refuses to act."""
    _ = tmp_path
    module = _import()

    confirmation = module.confirm_supersession(
        orphan=_orphan(run_id=_FIRST_RUN),
        journaled=JournaledRuns(
            newest_run_id_by_item={_ITEM_ID: _SECOND_RUN},
            item_id_by_run={},
        ),
    )

    assert confirmation.hold_reason == module.HOLD_REASON_SUPERSESSION_UNCONFIRMED
    assert confirmation.newest_run_id is None


def test_a_journal_that_no_longer_names_the_item_holds(tmp_path: Path) -> None:
    """A fresh read naming no run for the item is no evidence of a supersession."""
    module = _import()
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN, _SECOND_RUN])
    journaled = read_journaled_runs(path=journal)
    journal.write_text("", encoding="utf-8")

    confirmation = module.confirm_supersession(
        orphan=_orphan(run_id=_FIRST_RUN),
        journaled=journaled,
    )

    assert confirmation.hold_reason == module.HOLD_REASON_SUPERSESSION_UNCONFIRMED
    assert confirmation.newest_run_id is None


def test_an_orphan_on_another_reason_is_confirmed_without_a_re_read() -> None:
    """Only the `superseded-run` arm depends on the snapshot, so only it is re-read.

    The snapshot handed in names no source, which the arm above holds on; an
    `item-not-active` orphan passing anyway is what proves the re-read was
    never reached.
    """
    module = _import()

    confirmation = module.confirm_supersession(
        orphan=_orphan(run_id=_FIRST_RUN, reason=ORPHAN_REASON_ITEM_NOT_ACTIVE),
        journaled=JournaledRuns(newest_run_id_by_item={}, item_id_by_run={}),
    )

    assert (confirmation.hold_reason, confirmation.newest_run_id) == (None, None)


def test_the_declined_cancellation_is_journaled_under_its_own_hold_reason(
    tmp_path: Path,
) -> None:
    """A hold nobody can see is the failure the journal row exists to end.

    The reason has to be distinct from the grace arm's two holds, because those
    say a human decision is still waiting while this one says the sweep's own
    evidence was older than the run it was judging.
    """
    module = _import()
    journal_writer = _Journal()
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    inputs = _inputs(
        tmp_path=tmp_path,
        journal_path=journal,
        runner=_Runner(ps_rows=_ps(run_id=_SECOND_RUN)),
        transport=_Transport(),
        journal=journal_writer,
    )
    _append_stamps(path=journal, run_ids=[_SECOND_RUN])

    summary = reconcile.reconcile_runs(inputs=inputs, factories=[_HP])

    assert summary.reconciled == ()
    assert [row["stage"] for row in journal_writer.written] == [_HOLD_STAGE]
    assert _records_module().JOURNAL_STAGE_SUPERSESSION_HOLD == _HOLD_STAGE
    row = journal_writer.written[0]
    assert row["hold_reason"] == module.HOLD_REASON_SUPERSESSION_UNCONFIRMED
    assert row["hold_reason"] not in (BLOCKED_HOLD_WITHIN_GRACE, BLOCKED_HOLD_UNMEASURED)
    assert (row["run_id"], row["newest_journaled_run_id"]) == (_SECOND_RUN, _SECOND_RUN)
    assert row["orphan_reason"] == ORPHAN_REASON_SUPERSEDED_RUN


def test_a_dry_run_declines_the_cancellation_without_journaling_it(tmp_path: Path) -> None:
    """A dry run projects the same decision and writes nothing, as every dry run does."""
    journal_writer = _Journal()
    journal = _stamped(tmp_path=tmp_path, run_ids=[_FIRST_RUN])
    inputs = _inputs(
        tmp_path=tmp_path,
        journal_path=journal,
        runner=_Runner(ps_rows=_ps(run_id=_SECOND_RUN)),
        transport=_Transport(),
        journal=journal_writer,
    )
    _append_stamps(path=journal, run_ids=[_SECOND_RUN])

    summary = reconcile.reconcile_runs(inputs=inputs, factories=[_HP], dry_run=True)

    assert summary.reconciled == ()
    assert journal_writer.written == []


def _import() -> Any:
    assert _MODULE_PATH.is_file(), f"the supersession module does not exist: {_MODULE_PATH}"
    return importlib.import_module(_MODULE)


def _records_module() -> Any:
    return importlib.import_module(_RECORDS_MODULE)


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
    ledger: _Ledger | None = None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=[_item(status="active")],
        journaled=read_journaled_runs(path=journal_path),
        runner=runner,
        journal=_Journal() if journal is None else journal,
        ledger=_Ledger() if ledger is None else ledger,
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


def _ps(*, run_id: str, status_kind: str = "running") -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": f"Work-item: {_ITEM_ID}\nRepo: /tmp/repo",
                "status": {"kind": status_kind},
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

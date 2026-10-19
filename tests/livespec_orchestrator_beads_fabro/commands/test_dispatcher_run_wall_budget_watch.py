"""Exporting before cancelling a run past its wall budget (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "When the budget is exceeded, the Dispatcher MUST first
export the run's record under the export-then-terminate precondition ...
writing and reading back the preserve-by-reference pointer. Only then MUST it
cancel the run; cancelling the run is what releases its slot."

THE ORDER IS THE WHOLE POINT. `fabro rm -f` is what makes the run's record
unavailable, so an export attempted afterwards exports nothing -- and it would
still succeed, reporting a run whose work was destroyed as a run that had none.
The read-back is not ceremony either: `bd show --json` carries no comments at
all, so the obvious verification reports a successful write as lost.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
    RunWallStart,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch"
_RUN_ID = "01RUN"
_WORK_ITEM_ID = "bd-ib-sdxfsn"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
# `node_id` is the key the engine puts beside its stage envelope, and the
# key `executing_stage` reads: a fixture spelling it `node` would make the
# stage read as unnamed on a stream that plainly names it.
_EVENTS = (
    '[{"type": "stage.started", "node_id": "implement",' ' "timestamp": "2026-10-13T12:00:00Z"}]'
)
_INSPECT = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'


def _module_path() -> Path:
    """Where the budget watch module lives, beside the budget it enforces."""
    return Path(str(_node_timeouts.__file__)).with_name("_dispatcher_run_wall_budget_watch.py")


def _watch() -> Any:
    """The watch module, imported inside a test body rather than at top."""
    assert _module_path().is_file(), f"{_module_path()} does not exist"
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    """A CommandRunner scripting the fabro verbs the budget cancel issues.

    Every call is appended to `calls` in order, which is what makes the
    export-before-terminate ordering assertable rather than merely plausible.
    """

    calls: list[str] = field(default_factory=list)
    dump_exit_code: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        verb = argv[1] if len(argv) > 1 else ""
        self.calls.append(verb)
        stdout = {"events": _EVENTS, "inspect": _INSPECT}.get(verb, "")
        exit_code = self.dump_exit_code if verb == "dump" else 0
        return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


@dataclass(kw_only=True)
class _FakeLedger:
    """The narrow comment surface the export writes and reads back through."""

    comments: list[dict[str, Any]] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    swallow_writes: bool = False

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.reads.append(issue_id)
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.writes.append(issue_id)
        if self.swallow_writes:
            return
        self.comments.append({"id": "comment-9173", "text": body})


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=_SERVER,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
    )


def _port(*, repo: Path, runner: _ScriptedRunner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url=_SERVER),
        runner=runner,
        cwd=repo,
    )


def _cancelled(
    *,
    tmp_path: Path,
    runner: _ScriptedRunner,
    ledger: _FakeLedger,
    now_epoch: float,
) -> tuple[Any, _RecordingJournal]:
    watch = _watch()
    journal = _RecordingJournal()
    verdict = watch.cancel_run_past_budget(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=RunWallStart(epoch=_START_EPOCH, source=RUN_RECORD_SOURCE),
        now_epoch=now_epoch,
        ledger=cast("Any", ledger),
    )
    return verdict, journal


def test_the_pointer_is_written_and_read_back_before_the_run_is_cancelled(
    tmp_path: Path,
) -> None:
    """The export lands, is verified by read-back, and only then is `rm` issued."""
    watch = _watch()
    runner = _ScriptedRunner()
    ledger = _FakeLedger()
    verdict, journal = _cancelled(
        tmp_path=tmp_path,
        runner=runner,
        ledger=ledger,
        now_epoch=_START_EPOCH + 3601.0,
    )
    assert verdict == watch.RunWallVerdict.CANCELLED
    assert "rm" in runner.calls
    # The export's own `fabro dump` precedes the `rm`, and the ledger write and
    # its read-back both land before it too.
    assert runner.calls.index("dump") < runner.calls.index("rm")
    assert ledger.writes == [_WORK_ITEM_ID]
    assert len(ledger.reads) == 2
    assert ledger.comments[0]["text"].startswith(PRESERVE_POINTER_MARKER)
    records = [r for r in journal.records if r.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE]
    assert len(records) == 1
    assert records[0]["preserved_pointer"] == "comment-9173"
    assert records[0]["run_id"] == _RUN_ID
    assert records[0]["factory"] == "hp"
    assert records[0]["elapsed_seconds"] == 3601.0
    assert records[0]["budget_seconds"] == 3600.0
    assert records[0]["budget_layer"] == REPOSITORY_LAYER
    assert records[0]["executing_stage"] == "implement"
    # Never the stall cancel's record, whatever else this run was doing.
    assert all(r.get("stage") != STALL_CANCEL_STAGE for r in journal.records)


def test_a_run_within_its_budget_is_neither_exported_nor_cancelled(tmp_path: Path) -> None:
    """Under the budget the watch does nothing at all -- no probe, no write."""
    watch = _watch()
    runner = _ScriptedRunner()
    ledger = _FakeLedger()
    verdict, journal = _cancelled(
        tmp_path=tmp_path,
        runner=runner,
        ledger=ledger,
        now_epoch=_START_EPOCH + 3600.0,
    )
    assert verdict == watch.RunWallVerdict.WITHIN
    assert runner.calls == []
    assert ledger.writes == []
    assert journal.records == []


def test_a_pointer_that_does_not_read_back_leaves_the_run_running(tmp_path: Path) -> None:
    """No read-back, no cancel: the clause holds the cancel until it can.

    The write is ATTEMPTED and the run is left alone, which is the fail-closed
    direction: a slot held one more poll interval is recoverable, while a run
    destroyed with nothing durable naming its tree is not.
    """
    watch = _watch()
    runner = _ScriptedRunner()
    ledger = _FakeLedger(swallow_writes=True)
    verdict, journal = _cancelled(
        tmp_path=tmp_path,
        runner=runner,
        ledger=ledger,
        now_epoch=_START_EPOCH + 7200.0,
    )
    assert verdict == watch.RunWallVerdict.HELD
    assert ledger.writes == [_WORK_ITEM_ID]
    assert "rm" not in runner.calls
    assert all(record.get("stage") != RUN_WALL_BUDGET_EXCEEDED_STAGE for record in journal.records)


def test_a_resolvable_target_yields_the_ledger_the_export_writes_through(
    tmp_path: Path,
) -> None:
    """A target whose configuration resolves a tenant yields a comment surface.

    Asserted beside the None arm below, because the two are one claim: the
    cancel proceeds only where a ledger exists, so a resolver that answered
    None for every target would hold every budget cancel for ever while
    looking perfectly fail-closed.
    """
    watch = _watch()
    _ = (tmp_path / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "connection": {"prefix": "bd-ib", "tenant": "t", "fake": true}\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    ledger = watch.run_wall_ledger(repo=tmp_path)
    assert ledger is not None
    # The two verbs the export uses, and nothing wider: the resolver's job is
    # to answer WHETHER this host has a comment surface, never to exercise one.
    assert callable(ledger.list_comments)
    assert callable(ledger.add_comment)


def test_an_unresolvable_ledger_holds_the_cancel_rather_than_taking_it(tmp_path: Path) -> None:
    """A ledger this host cannot reach is a failed measurement, not a cancel.

    `run_wall_ledger` answers None for a target whose configuration does not
    resolve a tenant, and a cancel that proceeded on that answer would destroy
    a run with no durable pointer written anywhere.
    """
    watch = _watch()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    verdict = watch.cancel_run_past_budget(
        dispatch_id=None,
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=RunWallStart(epoch=_START_EPOCH, source=RUN_RECORD_SOURCE),
        now_epoch=_START_EPOCH + 7200.0,
        ledger=None,
    )
    assert verdict == watch.RunWallVerdict.HELD
    assert "rm" not in runner.calls
    assert watch.run_wall_ledger(repo=tmp_path) is None


def test_an_unfixed_start_is_within_budget_and_touches_nothing(tmp_path: Path) -> None:
    """An unmeasured slot-holding time cannot exceed anything."""
    watch = _watch()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    verdict = watch.cancel_run_past_budget(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=None,
        now_epoch=_START_EPOCH + 99_999.0,
        ledger=cast("Any", _FakeLedger()),
    )
    assert verdict == watch.RunWallVerdict.WITHIN
    assert runner.calls == []
    assert journal.records == []


def test_the_run_start_is_observed_from_the_runs_own_record(tmp_path: Path) -> None:
    """The start reading is taken through the port, once, when it is fixed."""
    watch = _watch()
    runner = _ScriptedRunner()
    start = watch.observe_run_wall_start(
        port=_port(repo=tmp_path, runner=runner),
        run_id=_RUN_ID,
        observed_at_epoch=_START_EPOCH,
    )
    # The scripted `inspect` carries no running instant, so the clock falls
    # back to the poll that observed the run running.
    assert start.epoch == _START_EPOCH
    assert start.source != RUN_RECORD_SOURCE
    assert runner.calls == ["inspect"]


def test_the_three_verdicts_are_distinct_values() -> None:
    """Held is not within, and neither is a cancel.

    Three values rather than a boolean because the launcher owes each a
    different act: fall through to the stall arm, keep waiting without
    cancelling on the stall rule, or end the dispatch on the budget.
    """
    watch = _watch()
    verdicts = {
        watch.RunWallVerdict.WITHIN,
        watch.RunWallVerdict.CANCELLED,
        watch.RunWallVerdict.HELD,
    }
    assert len(verdicts) == 3


def test_a_failed_export_dump_still_writes_a_pointer_and_cancels(tmp_path: Path) -> None:
    """A dump that could not run leaves a pointer stating so, and still cancels.

    The export-then-terminate precondition is satisfied by a pointer that was
    written and read back, not by a successful artifact: a run whose dump
    failed has a durable record naming the factory and the run, which is what
    an operator re-dispatching from it reads.
    """
    watch = _watch()
    runner = _ScriptedRunner(dump_exit_code=1)
    ledger = _FakeLedger()
    verdict, journal = _cancelled(
        tmp_path=tmp_path,
        runner=runner,
        ledger=ledger,
        now_epoch=_START_EPOCH + 7200.0,
    )
    assert verdict == watch.RunWallVerdict.CANCELLED
    assert ledger.comments[0]["text"].startswith(PRESERVE_POINTER_MARKER)
    assert [r["stage"] for r in journal.records] == [RUN_WALL_BUDGET_EXCEEDED_STAGE]

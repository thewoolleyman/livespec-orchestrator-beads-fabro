"""Holding a budget cancel until its export reads back (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "When the export cannot be read back, the Dispatcher
MUST NOT cancel the run. It MUST journal one `run-wall-budget-held` record
naming the run, the elapsed seconds, the budget and the failed measurement, and
MUST re-attempt the export on the next poll, cancelling only once a read-back
succeeds."

THE HELD ROW IS A MEASUREMENT FAILURE, NOT A CANCEL, which is why it names the
measurement rather than a stage or a publication: the run has not been
cancelled, so its own record has not been read, and rendering a stage or a
published head here would put a reading nobody took onto the one row that
exists to say a reading failed.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdict,
    cancel_run_past_budget,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
    RunWallStart,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_RECORDS_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records"
_RUN_ID = "01RUN"
_WORK_ITEM_ID = "bd-ib-sdxfsn"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
_NOW_EPOCH = _START_EPOCH + 7200.0
_INSPECT = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'


def _held_stage() -> str:
    """The held stage, read inside a test body rather than imported at top.

    Read off the module so the Red commit fails on a genuine assertion rather
    than at collection, which an absent top-level import would produce.
    """
    module = importlib.import_module(_RECORDS_MODULE)
    name = "RUN_WALL_BUDGET_HELD_STAGE"
    assert hasattr(module, name), f"{_RECORDS_MODULE} declares no {name}"
    return cast("str", module.RUN_WALL_BUDGET_HELD_STAGE)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    calls: list[str] = field(default_factory=list)

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
        return CommandResult(exit_code=0, stdout=_INSPECT if verb == "inspect" else "", stderr="")


@dataclass(kw_only=True)
class _FlakyLedger:
    """A comment surface whose first write does not read back, and whose second does.

    `pending` models the read-back failure the clause names: the write is
    attempted, the comment does not come back, and the NEXT poll finds it there
    -- which is also how a write that landed with a failed read-back converges
    rather than growing the ledger.
    """

    comments: list[dict[str, Any]] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.writes.append(issue_id)
        # The first write lands in `pending` and is only visible to the SECOND
        # poll, which is what a read-back that could not confirm a write looks
        # like from here.
        if self.pending:
            self.comments.extend(self.pending)
            self.pending = []
            return
        self.pending = [{"id": "comment-9173", "text": body}]


def _plan(*, repo: Path, server: str | None = _SERVER) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=server,
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


def _poll(
    *,
    tmp_path: Path,
    runner: _ScriptedRunner,
    journal: _RecordingJournal,
    ledger: Any,
    server: str | None = _SERVER,
) -> Any:
    return cancel_run_past_budget(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path, server=server),
        port=_port(repo=tmp_path, runner=runner),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        run_id=_RUN_ID,
        start=RunWallStart(epoch=_START_EPOCH, source=RUN_RECORD_SOURCE),
        now_epoch=_NOW_EPOCH,
        ledger=ledger,
    )


def test_a_pointer_that_does_not_read_back_journals_one_held_record(tmp_path: Path) -> None:
    """The held row names the run, the elapsed seconds, the budget and the failure."""
    held_stage = _held_stage()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    ledger = _FlakyLedger()
    verdict = _poll(tmp_path=tmp_path, runner=runner, journal=journal, ledger=ledger)
    assert verdict == RunWallVerdict.HELD
    held = [record for record in journal.records if record.get("stage") == held_stage]
    assert len(held) == 1
    assert held[0]["run_id"] == _RUN_ID
    assert held[0]["work_item_id"] == _WORK_ITEM_ID
    assert held[0]["elapsed_seconds"] == 7200.0
    assert held[0]["budget_seconds"] == 3600.0
    assert held[0]["budget_layer"] == REPOSITORY_LAYER
    failed = held[0]["failed_measurement"]
    assert isinstance(failed, str)
    assert "read back" in failed
    # Not a cancel: no `rm`, and no exceeded record on the journal.
    assert "rm" not in runner.calls
    assert all(r.get("stage") != RUN_WALL_BUDGET_EXCEEDED_STAGE for r in journal.records)


def test_the_export_is_re_attempted_and_the_second_read_back_cancels(tmp_path: Path) -> None:
    """A held poll leaves the run alive, and the next poll takes the cancel.

    No per-run state is needed for the re-attempt: the run is still running, so
    the following poll measures the same exceeded budget and performs the same
    export -- and the export locates an existing pointer rather than rewriting
    one, so the ledger does not grow per attempt.
    """
    held_stage = _held_stage()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    ledger = _FlakyLedger()
    first = _poll(tmp_path=tmp_path, runner=runner, journal=journal, ledger=ledger)
    second = _poll(tmp_path=tmp_path, runner=runner, journal=journal, ledger=ledger)
    assert (first, second) == (RunWallVerdict.HELD, RunWallVerdict.CANCELLED)
    assert "rm" in runner.calls
    stages = [record.get("stage") for record in journal.records]
    assert stages.count(held_stage) == 1
    assert stages.count(RUN_WALL_BUDGET_EXCEEDED_STAGE) == 1
    exceeded = next(
        record
        for record in journal.records
        if record.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE
    )
    assert exceeded["preserved_pointer"] == "comment-9173"
    assert len(ledger.comments) == 1


def test_an_unresolvable_ledger_names_itself_as_the_failed_measurement(
    tmp_path: Path,
) -> None:
    """A host with no ledger is a measurement failure with its own wording.

    Distinct from a read-back that failed, because the remedy differs: one is a
    configuration fault on the dispatching host and the other is a ledger that
    did not confirm a write.
    """
    held_stage = _held_stage()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    verdict = _poll(tmp_path=tmp_path, runner=runner, journal=journal, ledger=None)
    assert verdict == RunWallVerdict.HELD
    held = [record for record in journal.records if record.get("stage") == held_stage]
    failed = held[0]["failed_measurement"]
    assert isinstance(failed, str)
    assert "ledger" in failed
    assert runner.calls == []


def test_a_factory_declaring_no_server_names_itself_as_the_failed_measurement(
    tmp_path: Path,
) -> None:
    """With no server url there is nothing to export the run's record from."""
    held_stage = _held_stage()
    runner = _ScriptedRunner()
    journal = _RecordingJournal()
    verdict = _poll(
        tmp_path=tmp_path,
        runner=runner,
        journal=journal,
        ledger=cast("Any", _FlakyLedger()),
        server=None,
    )
    assert verdict == RunWallVerdict.HELD
    held = [record for record in journal.records if record.get("stage") == held_stage]
    failed = held[0]["failed_measurement"]
    assert isinstance(failed, str)
    assert "server" in failed
    assert runner.calls == []


def test_the_held_row_carries_no_stage_pull_request_or_published_head(
    tmp_path: Path,
) -> None:
    """A held poll has read nothing of the run, so it reports nothing of it."""
    held_stage = _held_stage()
    journal = _RecordingJournal()
    _ = _poll(
        tmp_path=tmp_path,
        runner=_ScriptedRunner(),
        journal=journal,
        ledger=cast("Any", _FlakyLedger()),
    )
    held = [record for record in journal.records if record.get("stage") == held_stage]
    assert "executing_stage" not in held[0]
    assert "pull_request" not in held[0]
    assert "published_head" not in held[0]
    assert held[0]["stage"] != RUN_WALL_BUDGET_EXCEEDED_STAGE

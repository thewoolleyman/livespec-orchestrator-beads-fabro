"""The engine's budget terminal, and the loop's held fall-through (bd-ib-sdxfsn).

Two arms of the launcher-side budget that the loop-driving cases in
`test_dispatcher_run_wall_budget_launcher.py` cannot reach without breaking the
thing they measure:

* the ENGINE routing a launcher's budget report to its own terminal, which is
  reached through `run_dispatch` rather than through `launch`; and
* the loop's HELD fall-through, which requires an export that does not read
  back -- the state in which the run keeps its slot for one more poll and must
  NOT be cancelled as stalled either.

THE HELD ARM IS THE ONE WORTH A CASE OF ITS OWN. A quiet run past its budget
satisfies the stall rule as well, so a `continue` that was ever a fall-through
would cancel it as stalled: the wrong record, the wrong disposition, and the
pointer the hold exists to secure still unwritten.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher,
    _dispatcher_watch_poll,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
    RUN_WALL_BUDGET_HELD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_RUN_ID = "01RUN"
_ITEM_ID = "bd-ib-budgetterm"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
_WALL_STEP = 3601.0
_FROZEN_EVENTS = '[{"timestamp": "2026-10-13T12:00:00Z"}]'
_INSPECT_RUNNING = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'
_PS_RUNNING = (
    f'[{{"run_id": "{_RUN_ID}", "goal": "Work-item: {_ITEM_ID}",' ' "status": {"kind": "running"}}]'
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _FakeLauncher:
    """A launcher that reports exactly what the watch loop decided."""

    result: FabroRunResult

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return self.result


@dataclass(kw_only=True)
class _RecordingRunner:
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _HeldScriptedRunner:
    """Scripts a running run whose budget export never reads back."""

    run_done: threading.Event = field(default_factory=threading.Event)
    calls: list[str] = field(default_factory=list)
    # The run ends on its OWN poll budget rather than on an `rm`, which is the
    # whole point of the case: nothing cancels it, so the double scripts no
    # `rm` arm for a verb it must never be asked for.
    polls_before_run_returns: int = 4
    _polls: int = 0

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
        if verb == "run":
            _ = self.run_done.wait(timeout=10.0)
            return CommandResult(exit_code=0, stdout=f"    Run: {_RUN_ID}\n", stderr="")
        if verb == "ps":
            return CommandResult(exit_code=0, stdout=_PS_RUNNING, stderr="")
        if verb == "inspect":
            self._polls += 1
            if self._polls >= self.polls_before_run_returns:
                self.run_done.set()
            return CommandResult(exit_code=0, stdout=_INSPECT_RUNNING, stderr="")
        if verb == "events":
            return CommandResult(exit_code=0, stdout=_FROZEN_EVENTS, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _NeverReadingLedger:
    """A comment surface whose writes are accepted and never read back."""

    writes: list[str] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        return []

    def add_comment(self, *, issue_id: str, body: str) -> None:
        _ = body
        self.writes.append(issue_id)


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=_SERVER,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
    )


def _wall_clock() -> Any:
    ticks = iter(_START_EPOCH + _WALL_STEP * step for step in range(5000))
    return lambda: next(ticks)


def _monotonic_clock() -> Any:
    ticks = iter(float(tick) for tick in range(0, 6_000_000, 600))
    return lambda: next(ticks)


def test_the_recording_runner_returns_for_a_direct_call(tmp_path: Path) -> None:
    """Exercise the shared recording runner's own body.

    The case below asserts that the runner is NEVER called -- the engine
    short-circuits on the budget report -- so the double's body is unreachable
    from it. Driving it once here is the pattern
    `test_dispatcher_watchdog.test_recording_runner_returns_for_a_direct_call`
    already established for exactly this shape.
    """
    runner = _RecordingRunner()
    out = runner.run(argv=["fabro", "ps"], cwd=tmp_path, timeout_seconds=1.0)
    assert (out.exit_code, runner.calls) == (0, [["fabro", "ps"]])


def test_the_engine_routes_a_budget_report_to_its_own_terminal(tmp_path: Path) -> None:
    """A launcher's budget report short-circuits the engine before any PR flow.

    The run has already been `fabro rm -f`-ed, so there is nothing left to
    inspect or publish -- which is why the runner is asserted untouched.
    """
    journal = _RecordingJournal()
    runner = _RecordingRunner()
    outcome = run_dispatch(
        plan=_plan(repo=tmp_path),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=3, interval_seconds=0.5),
        fabro_launcher=cast(
            "Any",
            _FakeLauncher(
                result=FabroRunResult(
                    command=CommandResult(
                        exit_code=124,
                        stdout="",
                        stderr="cancelled on the whole-run wall budget",
                    ),
                    budget_exceeded_run_id=_RUN_ID,
                )
            ),
        ),
    )
    assert outcome.status == RUN_WALL_BUDGET_EXCEEDED_STAGE
    assert outcome.stage == "fabro-run"
    assert outcome.fabro_run_id == _RUN_ID
    assert outcome.pr_number is None
    assert "3600" in outcome.detail
    assert REPOSITORY_LAYER in outcome.detail
    assert runner.calls == []
    assert [record.get("stage") for record in journal.records] == ["fabro-run"]


def test_a_held_export_keeps_the_run_and_never_cancels_it_as_stalled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A budget past its bound whose pointer never reads back cancels nothing.

    The event stream is frozen throughout, so this run satisfies the stall rule
    as well -- which is exactly what makes the held arm's `continue` a
    behaviour rather than a formality: a fall-through would cancel it as
    stalled, with the wrong record and the wrong disposition.
    """
    ledger = _NeverReadingLedger()
    monkeypatch.setattr(
        _dispatcher_io_fabro_launcher,
        "run_wall_ledger",
        lambda **_: ledger,
    )
    # The reaper reads the LEDGER for the item's status, which this repo has no
    # tenant for; declining it keeps this case about the budget rather than
    # about the item's lifecycle.
    monkeypatch.setattr(_dispatcher_watch_poll, "stale_item_reap", lambda **_: None)
    runner = _HeldScriptedRunner()
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=_monotonic_clock(),
        wall_clock=_wall_clock(),
        dispatch_id="dispatch-01",
    )
    result = launcher.launch(
        plan=_plan(repo=tmp_path),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
    )
    assert result.budget_exceeded_run_id is None
    assert result.stalled_run_id is None
    assert "rm" not in runner.calls
    stages = [record.get("stage") for record in journal.records]
    assert RUN_WALL_BUDGET_HELD_STAGE in stages
    assert RUN_WALL_BUDGET_EXCEEDED_STAGE not in stages
    assert STALL_CANCEL_STAGE not in stages
    # The export was ATTEMPTED on every poll past the budget, which is the
    # re-attempt the clause requires rather than a one-shot that gives up.
    assert len(ledger.writes) >= 2
    held = [
        json.loads(json.dumps(record))
        for record in journal.records
        if record.get("stage") == RUN_WALL_BUDGET_HELD_STAGE
    ]
    assert held[0]["budget_seconds"] == 3600.0
    assert "read back" in cast("str", held[0]["failed_measurement"])

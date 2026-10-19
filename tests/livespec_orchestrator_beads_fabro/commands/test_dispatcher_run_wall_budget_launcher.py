"""The whole-run wall budget as the watch loop applies it (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "When the run's `running` instant cannot be read and no
poll has yet observed it `running`, the budget is unmeasured, and the watchdog
MUST NOT cancel on it."

THE GUARANTEE IS STRUCTURAL. The clock is fixed on the FIRST poll that observed
the run `running`, so a run the factory never reported running has no start for
any elapsed figure to be measured from -- there is no expression in the loop
that could charge one. The positive control beside it is what keeps that from
being a vacuous claim: a run the factory DID report running, past its budget, is
cancelled through the same loop with the same clock.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine_journal
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_RUN_ID = "01RUN"
_ITEM_ID = "bd-ib-budgetlaunch"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
# One wall-clock reading per poll, each a full budget past the one before, so
# the FIRST measured poll is already past the budget.
_WALL_STEP = 3601.0
# Each poll's event stream carries the same timestamp, which is the only
# condition `decide_stall` confirms a stall on -- so a run reaching the stall
# arm WOULD be cancelled as stalled, and a budget cancel beside it is the
# budget arm acting first rather than the stall arm declining.
_FROZEN_EVENTS = '[{"timestamp": "2026-10-13T12:00:00Z"}]'
_PS_ROW_TEMPLATE = (
    '[{{"run_id": "{run}", "goal": "Work-item: {item}", "status": {{"kind": "{kind}"}}}}]'
)
_INSPECT_TEMPLATE = '[{{"run_id": "{run}", "status": {{"kind": "{kind}"}}}}]'


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
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
    _ = (tmp_path / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "connection": {"prefix": "bd-ib", "tenant": "t", "fake": true}\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="active",
            title="A dispatched slice the budget watch is driving",
            description="Implement the slice.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee="fabro",
            depends_on=(),
            captured_at="2026-10-13T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The dispatched slice is verified green.",
        ),
    )
    return tmp_path


def _budget_outcome() -> Any:
    """The engine's budget terminal builder, read inside a test body.

    Read off the module rather than imported at top so the Red commit fails on
    a genuine assertion rather than at collection.
    """
    name = "run_wall_budget_outcome"
    assert hasattr(
        _dispatcher_engine_journal, name
    ), f"{_dispatcher_engine_journal.__name__} declares no {name}"
    return _dispatcher_engine_journal.run_wall_budget_outcome


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedFabroRunner:
    """A CommandRunner scripting the verbs the watch loop and its budget issue.

    `fabro run` BLOCKS until the scripted poll budget is spent or the run is
    `rm`-ed, so the background thread stays alive while the foreground watch
    loop runs. Never launches a real process.
    """

    status_kind: str
    polls_before_run_returns: int = 4
    run_done: threading.Event = field(default_factory=threading.Event)
    calls: list[str] = field(default_factory=list)
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
        if verb == "rm":
            self.run_done.set()
            return CommandResult(exit_code=0, stdout="", stderr="")
        if verb == "ps":
            return CommandResult(
                exit_code=0,
                stdout=_PS_ROW_TEMPLATE.format(run=_RUN_ID, item=_ITEM_ID, kind=self.status_kind),
                stderr="",
            )
        if verb == "inspect":
            self._polls += 1
            if self._polls >= self.polls_before_run_returns:
                self.run_done.set()
            return CommandResult(
                exit_code=0,
                stdout=_INSPECT_TEMPLATE.format(run=_RUN_ID, kind=self.status_kind),
                stderr="",
            )
        if verb == "events":
            return CommandResult(exit_code=0, stdout=_FROZEN_EVENTS, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _wall_clock() -> Any:
    """A wall clock that jumps one full budget per reading."""
    ticks = iter(_START_EPOCH + _WALL_STEP * step for step in range(5000))
    return lambda: next(ticks)


def _monotonic_clock() -> Any:
    """A monotonic clock for the liveness samples, advancing 600s per reading."""
    ticks = iter(float(tick) for tick in range(0, 6_000_000, 600))
    return lambda: next(ticks)


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


def _launched(*, tmp_path: Path, status_kind: str) -> tuple[Any, _RecordingJournal, Any]:
    repo = _repo(tmp_path=tmp_path)
    runner = _ScriptedFabroRunner(status_kind=status_kind)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=_monotonic_clock(),
        wall_clock=_wall_clock(),
        dispatch_id="dispatch-01",
    )
    result = launcher.launch(
        plan=_plan(repo=repo),
        runner=cast("Any", runner),
        journal=cast("Any", journal),
    )
    return result, journal, runner


def test_a_run_never_reported_running_is_not_cancelled_on_the_budget(
    tmp_path: Path,
) -> None:
    """A `runnable` run has no fixed clock, so no elapsed figure exists to exceed.

    The wall clock advances a full budget per poll throughout, so a loop that
    measured from anything other than a running observation would cancel on the
    very first poll.
    """
    result, journal, runner = _launched(tmp_path=tmp_path, status_kind="runnable")
    assert result.budget_exceeded_run_id is None
    assert "rm" not in runner.calls
    stages = [record.get("stage") for record in journal.records]
    assert RUN_WALL_BUDGET_EXCEEDED_STAGE not in stages
    assert "run-wall-budget-held" not in stages


def test_a_running_run_past_its_budget_is_cancelled_through_the_same_loop(
    tmp_path: Path,
) -> None:
    """The positive control: the loop does cancel when the clock IS fixed."""
    result, journal, runner = _launched(tmp_path=tmp_path, status_kind="running")
    assert result.budget_exceeded_run_id == _RUN_ID
    assert result.stalled_run_id is None
    assert "rm" in runner.calls
    exceeded = [
        record
        for record in journal.records
        if record.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE
    ]
    assert len(exceeded) == 1
    assert exceeded[0]["run_id"] == _RUN_ID
    assert exceeded[0]["dispatch_id"] == "dispatch-01"
    assert exceeded[0]["budget_seconds"] == 3600.0
    assert exceeded[0]["budget_layer"] == REPOSITORY_LAYER
    assert isinstance(exceeded[0]["preserved_pointer"], str)
    # The budget arm acted, not the stall arm -- though the frozen event stream
    # means this run would also have satisfied the stall rule.
    assert all(record.get("stage") != STALL_CANCEL_STAGE for record in journal.records)


def test_the_budget_outcome_names_the_budget_and_the_way_out(tmp_path: Path) -> None:
    """The engine's own terminal for a budget cancel, distinct from the stall's.

    Its own status rather than the stall status, because the two carry opposite
    dispositions: a stall's first cancel releases the item to `ready` and a
    budget cancel rests it for a person. Its detail names the measurement and
    the key an operator would raise, because the terminal is what a dispatch
    RESULT reports and the journal row it points at is per-clone.
    """
    repo = _repo(tmp_path=tmp_path)
    outcome = _budget_outcome()(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=repo),
        run_id=_RUN_ID,
    )
    assert outcome.status == RUN_WALL_BUDGET_EXCEEDED_STAGE
    assert outcome.fabro_run_id == _RUN_ID
    assert outcome.stage == "fabro-run"
    assert "3600" in outcome.detail
    assert REPOSITORY_LAYER in outcome.detail
    assert "run_wall_budget_seconds" in outcome.detail
    assert RUN_WALL_BUDGET_EXCEEDED_STAGE in outcome.detail


def test_the_dispatch_journal_records_this_runs_budget_decision(tmp_path: Path) -> None:
    """Every launch's budget figures are on the record, not only a cancel's.

    Asserted through the cancel row rather than a second row, because the
    resolved budget is already journaled with the dispatch record at
    materialization: a second per-launch row would be the same figure recorded
    twice, and two rows that could disagree are worse than one.
    """
    _, journal, _ = _launched(tmp_path=tmp_path, status_kind="running")
    rows = [
        json.loads(json.dumps(record))
        for record in journal.records
        if record.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE
    ]
    assert rows[0]["elapsed_seconds"] > rows[0]["budget_seconds"]
    assert rows[0]["budget_start_source"] in {"run-record", "first-running-poll"}

"""A reattached run keeps the progress-stall watchdog active."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine as engine
from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_reattach as reattach
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_fabro_reattach_stall_watch as stall_watch,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_fabro_reattach_watch as reattach_watch,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_wall_budget_preserve,
    _dispatcher_run_wall_budget_watch,
    _dispatcher_stall_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    FabroRunResult,
    PollPolicy,
    reattach_watch_terminal,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_reattach_terminal import (
    reattach_terminal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult


@dataclass(kw_only=True)
class _Runner:
    replies: list[CommandResult]

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
        return self.replies.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Budget:
    ledger: object | None

    def verdict(self, **_kwargs: object) -> object:
        return RunWallVerdict.WITHIN


@dataclass(kw_only=True)
class _SequenceBudget:
    ledger: object | None
    verdicts: list[object]
    calls: list[dict[str, object]] = field(default_factory=list)

    def verdict(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.verdicts.pop(0)


@dataclass(frozen=True, kw_only=True)
class _TerminalPort:
    """A port returning the terminal read that ends a setup-only observation."""

    result: FabroInspectResult

    def inspect(self, *, run_id: str, timeout_seconds: float) -> FabroInspectResult:
        _ = (run_id, timeout_seconds)
        return self.result


def _no_ledger(*, repo: Path) -> None:
    _ = repo


def test_a_quiet_reattached_run_within_its_budget_is_cancelled_as_stalled(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """The client disconnect does not exempt a live run from the stall rule."""
    monkeypatch.setattr(reattach, "RunWallBudgetWatch", _Budget, raising=False)
    monkeypatch.setattr(reattach, "run_wall_ledger", _no_ledger, raising=False)
    monkeypatch.setattr(
        stall_watch,
        "liveness_sample",
        lambda **_kwargs: LivenessSample(last_event_epoch=10.0, observed_at=20.0),
        raising=False,
    )
    monkeypatch.setattr(stall_watch, "decide_stall", lambda **_kwargs: StallVerdict.STALLED)
    monkeypatch.setattr(stall_watch, "quiet_window_seconds", lambda **_kwargs: 3600.0)
    monkeypatch.setattr(stall_watch, "cancel_stalled_run", lambda **_kwargs: True)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    result = reattach.inspect_run(
        plan=plan,
        runner=cast(
            Any,
            _Runner(
                replies=[
                    CommandResult(
                        exit_code=0,
                        stdout='[{"run_id":"01DROPPED","status":{"kind":"running"}}]',
                        stderr="",
                    ),
                    CommandResult(
                        exit_code=0,
                        stdout='[{"run_id":"01DROPPED","status":{"kind":"blocked"}}]',
                        stderr="",
                    ),
                ]
            ),
        ),
        journal=cast(Any, _Journal()),
        run_id="01DROPPED",
        follow_live=True,
        timing=reattach.ReattachTiming(sleep=lambda _seconds: None),
    )
    assert result.stalled_run_id == "01DROPPED"
    assert result.budget_exceeded_run_id is None


def test_reattach_uses_the_recorded_running_instant_and_retries_a_held_export(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """Budget supervision counts the slot time before the client stream dropped."""
    budgets: list[_SequenceBudget] = []

    def _budget(*, ledger: object | None) -> _SequenceBudget:
        value = _SequenceBudget(
            ledger=ledger,
            verdicts=[RunWallVerdict.HELD, RunWallVerdict.CANCELLED],
        )
        budgets.append(value)
        return value

    monkeypatch.setattr(reattach, "RunWallBudgetWatch", _budget, raising=False)
    monkeypatch.setattr(reattach, "run_wall_ledger", _no_ledger, raising=False)
    result = reattach.inspect_run(
        plan=build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-pxp2ve",
            workflow_toml=tmp_path / "workflow.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor",
        ),
        runner=cast(
            Any,
            _Runner(
                replies=[
                    CommandResult(
                        exit_code=0,
                        stdout='[{"run_id":"01DROPPED","running_at":100.0,"status":{"kind":"running"}}]',
                        stderr="",
                    ),
                    CommandResult(
                        exit_code=0,
                        stdout='[{"run_id":"01DROPPED","running_at":100.0,"status":{"kind":"running"}}]',
                        stderr="",
                    ),
                ]
            ),
        ),
        journal=cast(Any, _Journal()),
        run_id="01DROPPED",
        follow_live=True,
        timing=reattach.ReattachTiming(sleep=lambda _seconds: None, wall_clock=lambda: 5000.0),
    )
    assert result.budget_exceeded_run_id == "01DROPPED"
    assert budgets[0].calls[0]["recorded_epoch"] == 100.0
    assert len(budgets[0].calls) == 2


def test_reattach_budget_disposition_rests_the_item_for_a_human(*, tmp_path: Path) -> None:
    """The reattach result takes the same budget terminal as the foreground watch."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    outcome = reattach_watch_terminal(
        plan=plan,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=None,
            status_kind="running",
            failure=None,
            budget_exceeded_run_id="01DROPPED",
        ),
    )
    assert outcome is not None
    assert outcome.status == "run-wall-budget-exceeded"
    assert outcome.stage == "fabro-run"
    assert reattach_terminal(outcome_type=engine.DispatchOutcome, plan=plan, inspect=None) is None
    stalled = reattach_terminal(
        outcome_type=engine.DispatchOutcome,
        plan=plan,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=None,
            status_kind="running",
            failure=None,
            stalled_run_id="01DROPPED",
        ),
    )
    assert stalled is not None
    assert stalled.status == "stalled-no-progress"


def test_reattach_watch_lazy_dependencies_and_stall_cancel_are_exercised(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """Lazy imports retain the acyclic seam while forwarding all cancel inputs."""
    ledger = object()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        _dispatcher_run_wall_budget_preserve,
        "run_wall_ledger",
        lambda **_kwargs: ledger,
    )
    monkeypatch.setattr(
        _dispatcher_stall_cancel,
        "cancel_stalled_run",
        lambda **kwargs: calls.append(kwargs) or True,
    )
    monkeypatch.setattr(_dispatcher_run_wall_budget_watch, "RunWallBudgetWatch", _Budget)
    monkeypatch.setattr(
        reattach_watch,
        "fabro_port_for_plan",
        lambda **_kwargs: _TerminalPort(
            result=FabroInspectResult(
                command=CommandResult(exit_code=0, stdout="", stderr=""),
                payload=None,
                status_kind="blocked",
                failure=None,
            )
        ),
    )
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    observed = reattach_watch.observe_reattached_run(
        inputs=reattach_watch.ReattachObservationInputs(
            plan=plan,
            runner=cast(Any, _Runner(replies=[])),
            journal=cast(Any, _Journal()),
            run_id="01DROPPED",
            follow_live=False,
            timing=reattach_watch.ReattachTiming(sleep=lambda _seconds: None),
        )
    )
    assert observed.status_kind == "blocked"
    assert stall_watch.cancel_stalled_run(
        plan=plan,
        port=cast(Any, object()),
        journal=cast(Any, _Journal()),
        run_id="01DROPPED",
        quiet_seconds=30.0,
    )
    assert calls[0]["dispatch_id"] is None


def test_a_reattach_stall_terminal_short_circuits_the_dispatch_loop(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """The reattach engine terminal returns before parsing any subsequent outcome."""
    command = CommandResult(exit_code=1, stdout="", stderr="dropped")

    @dataclass(frozen=True, kw_only=True)
    class _Launcher:
        def launch(
            self,
            *,
            plan: object,
            runner: object,
            journal: object,
        ) -> FabroRunResult:
            _ = (plan, runner, journal)
            return FabroRunResult(command=command, run_id="01DROPPED")

    monkeypatch.setattr(
        engine,
        "inspect_after_run",
        lambda **_kwargs: FabroInspectResult(
            command=command,
            payload=None,
            status_kind="running",
            failure=None,
            stalled_run_id="01DROPPED",
        ),
    )
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    outcome = run_dispatch(
        plan=plan,
        runner=cast(Any, _Runner(replies=[])),
        journal=cast(Any, _Journal()),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=cast(Any, _Launcher()),
    )
    assert outcome.status == "stalled-no-progress"

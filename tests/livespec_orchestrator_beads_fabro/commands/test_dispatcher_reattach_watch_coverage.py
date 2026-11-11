"""Coverage for the run-watch state that survives a dropped client stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_fabro_reattach as reattach,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_fabro_unobservable as unobservable,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_post_run_terminal as post_run_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_run_watch_decision as decision_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    LivenessState,
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_watch_decision import (
    ReattachRun,
    RunWatchDecision,
    decide_run_watch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdictValue,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watched_launch_result import (
    WatchResult,
    watched_launch_result,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult


def _plan(*, repo: Path) -> Any:
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-pxp2ve",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
    )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


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


def test_reattach_retains_a_pre_drop_watch_and_retries_a_held_budget(*, tmp_path: Path) -> None:
    """A later observer reuses the watch instead of starting a younger clock."""

    @dataclass(kw_only=True)
    class _Watch:
        decisions: list[RunWatchDecision]
        observed: int = 0

        def observe_liveness(self, **_kwargs: object) -> None:
            self.observed += 1

        def decide(self, **_kwargs: object) -> RunWatchDecision:
            return self.decisions.pop(0)

    watch = _Watch(decisions=[RunWatchDecision(), RunWatchDecision(budget_exceeded=True)])
    result = reattach.inspect_run(
        plan=_plan(repo=tmp_path),
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
                        stdout='[{"run_id":"01DROPPED","status":{"kind":"running"}}]',
                        stderr="",
                    ),
                ]
            ),
        ),
        journal=cast(Any, _Journal()),
        run_id=ReattachRun(run_id="01DROPPED", watch_state=cast(Any, watch)),
        follow_live=True,
        timing=reattach.ReattachTiming(sleep=lambda _seconds: None),
    )

    assert result is not None
    assert result.budget_exceeded_run_id == "01DROPPED"
    assert watch.observed == 2


def test_reattach_none_is_an_explicit_path(*, tmp_path: Path) -> None:
    assert (
        reattach.inspect_run(
            plan=_plan(repo=tmp_path),
            runner=cast(Any, _Runner(replies=[])),
            journal=cast(Any, _Journal()),
            run_id=None,
        )
        is None
    )


def test_liveness_falls_back_to_an_unmeasured_sample_without_a_bound_run(*, tmp_path: Path) -> None:
    sample = liveness_sample(
        plan=_plan(repo=tmp_path),
        port=cast(Any, object()),
        run_id=None,
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=10.0,
        state=LivenessState(),
    )

    assert sample.last_event_epoch is None
    assert sample.observed_at == 10.0


@pytest.mark.parametrize(
    ("verdict", "stall", "cancel", "expected"),
    [
        (RunWallVerdict.CANCELLED, False, False, RunWatchDecision(budget_exceeded=True)),
        (RunWallVerdict.HELD, True, True, RunWatchDecision()),
        (RunWallVerdict.WITHIN, True, True, RunWatchDecision(stalled=True)),
        (RunWallVerdict.WITHIN, False, False, RunWatchDecision()),
    ],
)
def test_run_watch_decision_keeps_budget_precedence(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: object,
    stall: bool,
    cancel: bool,
    expected: RunWatchDecision,
) -> None:
    @dataclass(kw_only=True)
    class _Budget:
        value: object

        def verdict(self, **_kwargs: object) -> object:
            return self.value

    def _decide_stall(
        *, samples: tuple[LivenessSample, ...], stall_seconds: float
    ) -> StallVerdictValue:
        _ = (samples, stall_seconds)
        return (
            decision_module.StallVerdict.STALLED if stall else decision_module.StallVerdict.CONTINUE
        )

    def _cancel_stalled_run(
        *,
        dispatch_id: str | None,
        plan: object,
        port: object,
        journal: object,
        run_id: str,
        quiet_seconds: float | None,
    ) -> bool:
        _ = (dispatch_id, plan, port, journal, run_id, quiet_seconds)
        return cancel

    monkeypatch.setattr(decision_module, "decide_stall", _decide_stall)
    monkeypatch.setattr(decision_module, "cancel_stalled_run", _cancel_stalled_run)

    observed = decide_run_watch(
        budget=cast(Any, _Budget(value=verdict)),
        dispatch_id=None,
        plan=_plan(repo=tmp_path),
        port=cast(Any, object()),
        runner=cast(Any, object()),
        journal=cast(Any, _Journal()),
        run_id="01DROPPED",
        recorded_epoch=None,
        now_epoch=0.0,
        samples=(),
        stall_seconds=1.0,
    )

    assert observed == expected


@pytest.mark.parametrize(
    ("run_id", "inspect", "client_text", "expected_status"),
    [
        (None, None, "", None),
        ("01DROPPED", None, "", None),
        (
            "01DROPPED",
            FabroInspectResult(
                command=CommandResult(exit_code=0, stdout="", stderr=""),
                payload=None,
                status_kind="failed",
                failure=None,
            ),
            "",
            None,
        ),
        (
            "01DROPPED",
            FabroInspectResult(
                command=CommandResult(exit_code=1, stdout="", stderr=""),
                payload=None,
                status_kind=None,
                failure=None,
            ),
            "LIVESPEC_NEEDS_HUMAN: terminal",
            None,
        ),
        (
            "01DROPPED",
            FabroInspectResult(
                command=CommandResult(exit_code=1, stdout="", stderr=""),
                payload=None,
                status_kind=None,
                failure=None,
            ),
            "unreadable",
            "run-unobservable",
        ),
    ],
)
def test_unobservable_outcome_only_retains_a_nonterminal_unreadable_run(
    *,
    tmp_path: Path,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    client_text: str,
    expected_status: str | None,
) -> None:
    outcome = unobservable.unobservable_run_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=tmp_path),
        run_id=run_id,
        inspect=inspect,
        client_text=client_text,
    )

    if expected_status is None:
        assert outcome is None
    else:
        assert outcome is not None
        assert outcome.status == expected_status


def test_post_run_terminal_returns_the_reattach_budget_disposition(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(repo=tmp_path)
    inspect = FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=None,
        status_kind="running",
        failure=None,
        budget_exceeded_run_id="01DROPPED",
    )
    terminal = post_run_module.reattach_terminal(plan=plan, inspect=inspect)
    assert terminal is not None

    def _inspect_after_run(**_kwargs: object) -> FabroInspectResult:
        return inspect

    def _reconcile_terminal_publication(**_kwargs: object) -> Any:
        from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_publication import (
            TerminalPublication,
        )

        return TerminalPublication(
            hold="unreadable", view=None, pr_view_error=None, refusal=terminal
        )

    monkeypatch.setattr(post_run_module, "inspect_after_run", _inspect_after_run)
    monkeypatch.setattr(
        post_run_module, "reconcile_terminal_publication", _reconcile_terminal_publication
    )

    result = post_run_module.post_run_terminal(
        plan=plan,
        runner=cast(Any, object()),
        journal=cast(Any, _Journal()),
        launched=FabroRunResult(
            command=CommandResult(exit_code=1, stdout="", stderr="dropped"),
            run_id="01DROPPED",
        ),
        sleep=lambda _seconds: None,
    )

    assert result.refusal == terminal


def test_watched_result_preserves_the_watch() -> None:
    @dataclass(kw_only=True)
    class _Thread:
        joined: bool = False

        def join(self, timeout: float | None = None) -> None:
            _ = timeout
            self.joined = True

    thread = _Thread()
    watch = cast(Any, object())
    result = watched_launch_result(
        watched=WatchResult(run_watch_state=watch),
        thread=cast(Any, thread),
        holder={"result": CommandResult(exit_code=0, stdout="", stderr="")},
        run_id_holder={"run_id": "01DROPPED"},
    )

    assert thread.joined
    assert result.run_watch_state is watch

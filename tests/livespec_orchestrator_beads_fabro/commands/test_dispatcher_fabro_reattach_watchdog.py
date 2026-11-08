"""The re-attach watcher keeps the whole-run wall budget in force."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_reattach as reattach
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_RUN_ID = "01DROPPED"
_ITEM_ID = "bd-ib-pxp2ve"


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
    calls: list[dict[str, object]] = field(default_factory=list)

    def verdict(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return RunWallVerdict.CANCELLED


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
        run_wall_budget=RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER),
    )


def test_a_live_run_past_its_budget_after_a_client_drop_is_reported_as_budget_cancelled(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """Re-attach hands the budget terminal back to the dispatch engine."""
    assert (
        "wall_clock" in reattach.ReattachTiming.__dataclass_fields__
    ), "Reattach timing must carry the wall clock the whole-run budget measures against"
    budgets: list[_Budget] = []

    def _budget(*, ledger: object | None, **_kwargs: object) -> _Budget:
        value = _Budget(ledger=ledger)
        budgets.append(value)
        return value

    def _no_ledger(*, repo: Path) -> None:
        _ = repo

    monkeypatch.setattr(reattach, "RunWallBudgetWatch", _budget, raising=False)
    monkeypatch.setattr(reattach, "run_wall_ledger", _no_ledger, raising=False)
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
                    )
                ]
            ),
        ),
        journal=cast(Any, _Journal()),
        run_id=_RUN_ID,
        follow_live=True,
        timing=reattach.ReattachTiming(sleep=lambda _seconds: None, wall_clock=lambda: 5000.0),
    )
    assert result.budget_exceeded_run_id == _RUN_ID
    assert result.stalled_run_id is None
    assert len(budgets) == 1
    assert budgets[0].calls[0]["run_id"] == _RUN_ID

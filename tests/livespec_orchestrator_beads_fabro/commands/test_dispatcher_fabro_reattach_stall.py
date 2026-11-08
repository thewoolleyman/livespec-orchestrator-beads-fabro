"""A reattached run keeps the progress-stall watchdog active."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_reattach as reattach
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
)


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


def _no_ledger(*, repo: Path) -> None:
    _ = repo


def test_a_quiet_reattached_run_within_its_budget_is_cancelled_as_stalled(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """The client disconnect does not exempt a live run from the stall rule."""
    monkeypatch.setattr(reattach, "RunWallBudgetWatch", _Budget, raising=False)
    monkeypatch.setattr(reattach, "run_wall_ledger", _no_ledger, raising=False)
    monkeypatch.setattr(
        reattach,
        "liveness_sample",
        lambda **_kwargs: LivenessSample(last_event_epoch=10.0, observed_at=20.0),
        raising=False,
    )
    monkeypatch.setattr(
        reattach, "decide_stall", lambda **_kwargs: StallVerdict.STALLED, raising=False
    )
    monkeypatch.setattr(reattach, "quiet_window_seconds", lambda **_kwargs: 3600.0, raising=False)
    monkeypatch.setattr(reattach, "cancel_stalled_run", lambda **_kwargs: True, raising=False)
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

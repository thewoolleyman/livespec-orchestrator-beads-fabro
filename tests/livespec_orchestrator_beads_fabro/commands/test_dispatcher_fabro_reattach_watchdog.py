"""The dropped-client observer retains the whole-run watch decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_reattach as reattach
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_watch_decision import (
    RunWatchDecision,
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


def test_a_reattached_run_returns_the_budget_disposition_from_the_shared_decision(
    *, tmp_path: Path, monkeypatch: Any
) -> None:
    """A client drop does not bypass the whole-run budget terminal."""
    assert hasattr(
        reattach, "RunWatchState"
    ), "reattach must carry the shared run-watch state after the client returns"

    @dataclass(kw_only=True)
    class _Watch:
        observed: list[object] = field(default_factory=list)

        def observe_liveness(self, **kwargs: object) -> None:
            self.observed.append(kwargs["record"])

        def decide(self, **_kwargs: object) -> RunWatchDecision:
            return RunWatchDecision(budget_exceeded=True)

    watch = _Watch()
    monkeypatch.setattr(reattach, "RunWatchState", lambda **_kwargs: watch)
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
        run_id="01DROPPED",
        follow_live=True,
        timing=reattach.ReattachTiming(sleep=lambda _seconds: None),
    )

    assert result.budget_exceeded_run_id == "01DROPPED"
    assert result.stalled_run_id is None
    assert watch.observed

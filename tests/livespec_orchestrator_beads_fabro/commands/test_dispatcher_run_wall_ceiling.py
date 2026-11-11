"""Resolution and progress evidence for the continuing run-wall budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_credential_window_resolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_ceiling import (
    PER_DISPATCH_ARGUMENT_LAYER,
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
    run_wall_ceiling_from_block,
    run_wall_ceiling_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_progress import (
    RunWallProgressInputs,
    run_wall_progress,
)

_BUDGET = RunWallBudget(seconds=100.0, layer=WORKFLOW_DEFAULT_LAYER)


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(argv)
        return self.result


def test_the_ceiling_resolves_each_layer_and_journals_its_source() -> None:
    """Default, repository, and argument values retain their resolution layers."""
    default = run_wall_ceiling_from_block(block={}, budget=_BUDGET)
    repository = run_wall_ceiling_from_block(
        block={"run_wall_ceiling_seconds": 250}, budget=_BUDGET
    )
    argument = run_wall_ceiling_from_block(
        block={"run_wall_ceiling_seconds": 250}, budget=_BUDGET, argument="300"
    )
    assert not isinstance(default, str)
    assert not isinstance(repository, str)
    assert not isinstance(argument, str)
    assert default.seconds == 300.0
    assert default.layer == WORKFLOW_DEFAULT_LAYER
    assert repository.seconds == 250.0
    assert repository.layer == REPOSITORY_LAYER
    assert argument.seconds == 300.0
    assert argument.layer == PER_DISPATCH_ARGUMENT_LAYER
    assert run_wall_ceiling_journal_record(ceiling=argument) == {
        "run_wall_ceiling": {"seconds": 300.0, "layer": PER_DISPATCH_ARGUMENT_LAYER}
    }


@pytest.mark.parametrize("value", [0, -1, True, "100"])
def test_an_invalid_committed_ceiling_is_refused_even_beside_an_argument(value: object) -> None:
    """A broken repository key is never hidden by the more-specific argument."""
    refusal = run_wall_ceiling_from_block(
        block={"run_wall_ceiling_seconds": value}, budget=_BUDGET, argument="300"
    )
    assert isinstance(refusal, str)
    assert "dispatcher.run_wall_ceiling_seconds" in refusal


@pytest.mark.parametrize("argument", ["0", "-1", "nope", "1.5"])
def test_an_invalid_argument_or_a_ceiling_under_budget_is_refused(argument: str) -> None:
    """The dispatch argument must be a positive integer and cannot undercut budget."""
    refusal = run_wall_ceiling_from_block(block={}, budget=_BUDGET, argument=argument)
    assert isinstance(refusal, str)
    assert "run-wall-ceiling-seconds" in refusal


def test_a_positive_ceiling_smaller_than_the_budget_is_refused() -> None:
    """The paired values and their sources are named before a run exists."""
    refusal = run_wall_ceiling_from_block(block={"run_wall_ceiling_seconds": 99}, budget=_BUDGET)
    assert isinstance(refusal, str)
    assert "99" in refusal
    assert "100" in refusal


def test_a_ceiling_resolution_fault_defers_through_the_credential_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window exposes an invalid ceiling to its owning admission gate."""

    def invalid_ceiling(*, block: dict[str, Any], budget: RunWallBudget) -> str:
        _ = (block, budget)
        return "dispatcher.run_wall_ceiling_seconds is invalid"

    monkeypatch.setattr(
        _dispatcher_credential_window_resolution, "run_wall_ceiling_from_block", invalid_ceiling
    )
    result = _dispatcher_credential_window_resolution.credential_use_window_from_block(block={})
    assert result == "dispatcher.run_wall_ceiling_seconds is invalid"


def test_an_unobservable_stream_or_capture_ref_never_counts_as_progress(tmp_path: Path) -> None:
    """Unreadable evidence takes the ordinary budget disposition rather than extending it."""
    failed = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="unavailable"))
    stream = run_wall_progress(
        inputs=RunWallProgressInputs(
            runner=cast("Any", failed),
            repo=tmp_path,
            work_item_id="bd-ib-pof4aa",
            run_id="run-1",
            seen_captures=set(),
            stream_observable=False,
            new_completions=(),
            now_epoch=100.0,
            window_seconds=10.0,
        )
    )
    capture = run_wall_progress(
        inputs=RunWallProgressInputs(
            runner=cast("Any", failed),
            repo=tmp_path,
            work_item_id="bd-ib-pof4aa",
            run_id="run-1",
            seen_captures=set(),
            stream_observable=True,
            new_completions=(),
            now_epoch=100.0,
            window_seconds=10.0,
        )
    )
    assert not stream.observable
    assert not capture.observable


def test_a_first_completion_is_progress_only_inside_its_window(tmp_path: Path) -> None:
    """No new capture falls back to a first-time completion in the progress window."""
    runner = _Runner(result=CommandResult(exit_code=0, stdout="", stderr=""))
    progress = run_wall_progress(
        inputs=RunWallProgressInputs(
            runner=cast("Any", runner),
            repo=tmp_path,
            work_item_id="bd-ib-pof4aa",
            run_id="run-1",
            seen_captures=set(),
            stream_observable=True,
            new_completions=(("janitor", 95.0),),
            now_epoch=100.0,
            window_seconds=10.0,
        )
    )
    assert progress.node == "janitor"
    assert progress.completed_at == 95.0


def test_a_capture_already_seen_in_this_run_does_not_extend_its_budget(tmp_path: Path) -> None:
    """Only a newly-created capture ref is autonomous progress evidence."""
    ref = "refs/livespec/wip/bd-ib-pof4aa/run-1/1"
    runner = _Runner(result=CommandResult(exit_code=0, stdout=f"{'a' * 40}\t{ref}\n", stderr=""))
    progress = run_wall_progress(
        inputs=RunWallProgressInputs(
            runner=cast("Any", runner),
            repo=tmp_path,
            work_item_id="bd-ib-pof4aa",
            run_id="run-1",
            seen_captures={ref},
            stream_observable=True,
            new_completions=(),
            now_epoch=100.0,
            window_seconds=10.0,
        )
    )
    assert progress.capture is None
    assert progress.node is None


def test_a_completion_outside_the_progress_window_does_not_extend_budget(tmp_path: Path) -> None:
    """A node completed before the window is not current autonomous progress."""
    runner = _Runner(result=CommandResult(exit_code=0, stdout="", stderr=""))
    progress = run_wall_progress(
        inputs=RunWallProgressInputs(
            runner=cast("Any", runner),
            repo=tmp_path,
            work_item_id="bd-ib-pof4aa",
            run_id="run-1",
            seen_captures=set(),
            stream_observable=True,
            new_completions=(("janitor", 80.0),),
            now_epoch=100.0,
            window_seconds=10.0,
        )
    )
    assert progress.node is None

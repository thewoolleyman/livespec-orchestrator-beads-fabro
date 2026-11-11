"""Progress evidence for a run that has exceeded its ordinary wall budget."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "RunWallCapture",
    "RunWallProgress",
    "RunWallProgressInputs",
    "run_wall_progress",
    "seed_run_wall_captures",
]

_REMOTE = "origin"
_PREFIX = "refs/livespec/wip"
_TIMEOUT_SECONDS = 5.0
_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class RunWallCapture:
    """One capture ref observed while grading the current budget poll."""

    ref: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class RunWallProgress:
    """One qualifying progress fact, or an unobservable/non-progress answer."""

    capture: RunWallCapture | None = None
    node: str | None = None
    completed_at: float | None = None
    observable: bool = True


@dataclass(kw_only=True)
class RunWallProgressInputs:
    """All facts needed to grade one poll's budget-progress evidence."""

    runner: CommandRunner
    repo: Path
    work_item_id: str
    run_id: str
    seen_captures: set[str]
    stream_observable: bool
    new_completions: tuple[tuple[str, float], ...]
    now_epoch: float
    window_seconds: float


def _latest_capture(*, inputs: RunWallProgressInputs) -> RunWallCapture | None | bool:
    """The run's highest capture, `None` when it has none, `False` when unreadable."""
    result = inputs.runner.run(
        argv=["git", "ls-remote", _REMOTE, f"{_PREFIX}/{inputs.work_item_id}/{inputs.run_id}/*"],
        cwd=inputs.repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return False
    refs = {
        fields[1]: fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }
    prefix = f"{_PREFIX}/{inputs.work_item_id}/{inputs.run_id}/"
    candidates = [
        (int(ref.removeprefix(prefix)), RunWallCapture(ref=ref, commit=commit))
        for ref, commit in refs.items()
        if ref.startswith(prefix) and ref.removeprefix(prefix).isdecimal()
    ]
    return None if not candidates else max(candidates, key=lambda value: value[0])[1]


def seed_run_wall_captures(*, inputs: RunWallProgressInputs) -> None:
    """Record the captures standing before the budget, so none of them reads as new.

    A capture created long before the progress window is not progress, and a
    ref listing carries no age; the baseline taken over the last window before
    the budget is what lets a past-budget poll tell a newly created capture from
    one that was already there. An unreadable listing seeds nothing.
    """
    capture = _latest_capture(inputs=inputs)
    if isinstance(capture, RunWallCapture):
        inputs.seen_captures.add(capture.ref)


def run_wall_progress(*, inputs: RunWallProgressInputs) -> RunWallProgress:
    """Read fresh captures and completion events; unreadable input is not progress."""
    if not inputs.stream_observable:
        return RunWallProgress(observable=False)
    capture = _latest_capture(inputs=inputs)
    if capture is False:
        return RunWallProgress(observable=False)
    if isinstance(capture, RunWallCapture) and capture.ref not in inputs.seen_captures:
        inputs.seen_captures.add(capture.ref)
        return RunWallProgress(capture=capture)
    for node, completed_at in inputs.new_completions:
        if inputs.now_epoch - completed_at <= inputs.window_seconds:
            return RunWallProgress(node=node, completed_at=completed_at)
    return RunWallProgress()

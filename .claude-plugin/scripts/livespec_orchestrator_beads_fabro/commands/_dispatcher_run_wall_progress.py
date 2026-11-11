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


def run_wall_progress(*, inputs: RunWallProgressInputs) -> RunWallProgress:
    """Read fresh captures and completion events; unreadable input is not progress."""
    if not inputs.stream_observable:
        return RunWallProgress(observable=False)
    result = inputs.runner.run(
        argv=["git", "ls-remote", _REMOTE, f"{_PREFIX}/{inputs.work_item_id}/{inputs.run_id}/*"],
        cwd=inputs.repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return RunWallProgress(observable=False)
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
    capture = None if not candidates else max(candidates, key=lambda value: value[0])[1]
    if capture is not None and capture.ref not in inputs.seen_captures:
        inputs.seen_captures.add(capture.ref)
        return RunWallProgress(capture=capture)
    for node, completed_at in inputs.new_completions:
        if inputs.now_epoch - completed_at <= inputs.window_seconds:
            return RunWallProgress(node=node, completed_at=completed_at)
    return RunWallProgress()

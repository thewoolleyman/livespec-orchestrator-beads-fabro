"""Tests for the Fabro launcher IO extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io,
    _dispatcher_io_fabro_launcher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan


def test_watched_launcher_remains_the_dispatcher_io_public_entry_point() -> None:
    assert _dispatcher_io.WatchedFabroLauncher is WatchedFabroLauncher


def test_watched_launcher_covers_finished_thread_watch_path(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @dataclass(kw_only=True)
    class _SynchronousThread:
        target: Callable[[], None]
        name: str
        daemon: bool = False

        def start(self) -> None:
            self.target()

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            _ = timeout

    @dataclass(kw_only=True)
    class _Runner:
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
        ) -> CommandResult:
            _ = (argv, cwd, timeout_seconds)
            return CommandResult(exit_code=0, stdout="done", stderr="")

    def _thread(*, target: Callable[[], None], name: str) -> _SynchronousThread:
        return _SynchronousThread(target=target, name=name)

    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-fcipkv",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=_Runner(),
        journal=object(),  # type: ignore[arg-type]
    )

    assert result.command.exit_code == 0
    assert result.command.stdout == "done"
    assert result.stalled_run_id is None

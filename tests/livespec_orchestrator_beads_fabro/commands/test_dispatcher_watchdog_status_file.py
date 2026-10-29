"""The progress watchdog's per-poll status read comes from a small status file, not the journal."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher,
    _dispatcher_stale_item_reap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

_ITEM_ID = "bd-ib-statusfile"
_POLLS = 3


@dataclass(kw_only=True)
class _Runner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv[1] == "ps":
            return CommandResult(
                exit_code=0,
                stdout=(
                    '[{"run_id": "01STATUS", "status": {"kind": "running"}, '
                    f'"goal": "Work-item: {_ITEM_ID}\\nRepo: /tmp/repo"}}]'
                ),
                stderr="",
            )
        if argv[1] == "inspect":
            return CommandResult(
                exit_code=0,
                stdout='[{"run_id": "01STATUS", "status": {"kind": "running"}}]',
                stderr="",
            )
        if argv[1] == "events":
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        return CommandResult(exit_code=0, stdout="Run: 01STATUS\n", stderr="")


@dataclass(kw_only=True)
class _PollingThread:
    target: Callable[[], None]
    name: str
    daemon: bool = False
    alive_checks: int = 0

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        self.alive_checks += 1
        return self.alive_checks < 2 * _POLLS + 1

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        self.target()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]]

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_every_watchdog_poll_reads_the_heartbeat_status_file_and_never_the_journal(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    journal_file = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    status_file = journal_file.with_name(f"{journal_file.stem}-otel-heartbeat.json")
    journal_file.parent.mkdir()
    _ = journal_file.write_text(
        json.dumps({"stage": "outcome", "work_item_id": _ITEM_ID}) + "\n", encoding="utf-8"
    )
    _ = status_file.write_text(json.dumps({_ITEM_ID: 1.0}), encoding="utf-8")
    opened: list[Path] = []
    original_open = Path.open

    def spy(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(self)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy)
    monkeypatch.setattr(
        _dispatcher_io_fabro_launcher.threading,
        "Thread",
        lambda *, target, name: _PollingThread(target=target, name=name),
    )
    monkeypatch.setattr(_dispatcher_stale_item_reap, "_work_item_status", lambda **_: "active")
    plan = build_plan(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    _ = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=lambda: 0.0,
        heartbeat_path=status_file,
    ).launch(plan=plan, runner=_Runner(), journal=_Journal(records=[]))

    assert opened.count(status_file) == _POLLS
    assert journal_file not in opened
    _ = journal_file.read_text(encoding="utf-8")
    assert journal_file in opened

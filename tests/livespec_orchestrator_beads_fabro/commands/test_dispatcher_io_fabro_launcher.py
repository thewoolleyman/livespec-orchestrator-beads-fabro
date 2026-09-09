"""Tests for the Fabro launcher IO extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io,
    _dispatcher_io_fabro_launcher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    STALL_SECONDS_ENV_VAR,
    LivenessSample,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroRunSummary
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(kw_only=True)
class _QueuedRunner:
    calls: list[str]
    rm_calls: list[str]
    reaped: bool = False

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
        command = argv[1]
        self.calls.append(command)
        if command == "ps":
            return CommandResult(
                exit_code=0,
                stdout=(
                    '[{"run_id": "01QUEUED", '
                    '"status": {"kind": "runnable"}, '
                    '"goal": "Work-item: bd-ib-queued\\nRepo: /tmp/repo"}]'
                ),
                stderr="",
            )
        if command == "rm":
            self.rm_calls.append(argv[3])
            self.reaped = True
            return CommandResult(exit_code=0, stdout="", stderr="")
        return CommandResult(exit_code=0, stdout="Run: 01QUEUED\n", stderr="")


@dataclass(kw_only=True)
class _QueuedThread:
    target: Callable[[], None]
    name: str
    runner: _QueuedRunner
    daemon: bool = False
    alive_checks: int = 0

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        self.alive_checks += 1
        return not self.runner.reaped and self.alive_checks < 3

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        if "run" not in self.runner.calls:
            self.target()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]]

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


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
            env: dict[str, str] | None = None,
            stdin: int | None = None,
        ) -> CommandResult:
            _ = (argv, cwd, timeout_seconds, env, stdin)
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


def test_queued_thread_join_skips_target_after_run_returns() -> None:
    calls: list[str] = []
    runner = _QueuedRunner(calls=["run"], rm_calls=[])
    thread = _QueuedThread(
        target=lambda: calls.append("target"),
        name="fabro-run-bd-ib-queued",
        runner=runner,
    )

    thread.join()

    assert calls == []


def test_watched_launcher_reaps_queued_run_after_item_closes(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(target=target, name=name, runner=runner)

    def _done_items(*, path: StoreConfig) -> list[WorkItem]:
        assert path.prefix == "bd-ib"
        assert path.repo_root == tmp_path
        return [
            WorkItem(
                id="bd-ib-queued",
                type="task",
                status="done",
                title="done",
                description="done",
                origin="freeform",
                gap_id=None,
                rank="a0",
                assignee=None,
                depends_on=(),
                captured_at="2026-08-16T00:00:00Z",
                resolution=None,
                reason=None,
                audit=None,
                superseded_by=None,
            )
        ]

    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])
    _write_livespec_config(repo=tmp_path)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(
        _dispatcher_io_fabro_launcher, "read_work_items", _done_items, raising=False
    )
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    assert runner.rm_calls == ["01QUEUED"]
    assert result.abandoned_run_id == "01QUEUED"
    assert result.abandoned_item_status == "done"
    # The unstamped dispatch names its own cause; the text is the stamp module's
    # to word, so it is read off the record rather than restated here.
    stamp_failure_detail = next(
        record["stamp_failure_detail"]
        for record in journal.records
        if record["stage"] == "dispatch-run-stamp"
    )
    assert isinstance(stamp_failure_detail, str)
    assert "record_dispatch_run" in stamp_failure_detail
    assert journal.records == [
        {
            "work_item_id": "bd-ib-queued",
            "stage": "watchdog-discovery-poll",
            "matched": True,
            "reason": "matched",
            "ps_exit_code": 0,
            "ps_row_count": 1,
            "work_item_row_count": 1,
            "unattributed_row_count": 0,
            "status_kinds": ["runnable"],
            "run_id": "01QUEUED",
            "status_kind": "runnable",
        },
        {
            "work_item_id": "bd-ib-queued",
            "stage": "dispatch-run-stamp",
            "run_id": "01QUEUED",
            "dispatch_factory": "default",
            "dispatch_factory_server": None,
            # The item is absent from the hermetic tenant, so the ledger write
            # fails open — and says so, rather than leaving the miss silent.
            "stamped": False,
            "stamp_failure_detail": stamp_failure_detail,
        },
        {
            "work_item_id": "bd-ib-queued",
            "stage": "stale-run-reap",
            "run_id": "01QUEUED",
            "item_status": "done",
            "rm_exit_code": 0,
        },
    ]


def test_watched_launcher_stamps_the_discovered_run_onto_its_work_item(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The ledger learns the run id while the run is still alive, not after it.

    `fabro run` is blocking and only yields its run id on RETURN, so a stamp
    written from the launcher's return value would land after the window in
    which anyone reconciling the factory needs it. The watchdog's own
    re-discovery poll is the first moment the id exists, and it is where the
    stamp is taken.
    """

    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(target=target, name=name, runner=runner)

    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])
    _write_livespec_config(repo=tmp_path)
    client = make_beads_client(config=store_config(repo=tmp_path))
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-queued",
            issue_type="task",
            title="queued",
            description="queued",
            assignee=None,
            created_at="2026-08-30T00:00:00Z",
        )
    )
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "_work_item_status", lambda **_: "done")
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp-xubuntu.perch-rudd.ts.net:32276",
    )

    _ = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    metadata = client.show_issue(issue_id="bd-ib-queued")["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["dispatch_fabro_run_id"] == "01QUEUED"
    assert metadata["dispatch_factory"] == {
        "name": "hp",
        "server": "https://hp-xubuntu.perch-rudd.ts.net:32276",
    }
    stamps = [record for record in journal.records if record["stage"] == "dispatch-run-stamp"]
    assert [record["stamped"] for record in stamps] == [True]


def test_watched_launcher_does_not_stall_cancel_queued_active_run(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )
    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])

    samples = [
        LivenessSample(last_event_epoch=100.0, observed_at=100.0),
        LivenessSample(last_event_epoch=100.0, observed_at=1200.0),
    ]

    def _next_sample(
        self: WatchedFabroLauncher,
        *,
        plan: object,
        port: object,
        run_id: str | None,
    ) -> LivenessSample:
        _ = (self, plan, port, run_id)
        return samples.pop(0)

    def _discover_runnable_run(self: WatchedFabroLauncher, **_: object) -> FabroRunSummary:
        _ = self
        return FabroRunSummary(
            run_id="01QUEUED",
            status_kind="runnable",
            goal=None,
            work_item_id="bd-ib-queued",
            total_usd_micros=None,
        )

    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(
            target=target,
            name=name,
            runner=runner,
            alive_checks=-2,
        )

    launcher = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0)
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "_work_item_status", lambda **_: "active")
    monkeypatch.setattr(WatchedFabroLauncher, "_sample", _next_sample)
    monkeypatch.setattr(WatchedFabroLauncher, "_discover_run", _discover_runnable_run)

    result = launcher.launch(plan=plan, runner=runner, journal=journal)

    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_skips_item_status_lookup_without_store_config(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(target=target, name=name, runner=runner)

    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])
    reader = Mock(return_value=[])
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "read_work_items", reader)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    assert result.abandoned_run_id is None
    assert runner.rm_calls == []
    assert reader.call_count == 0


def test_watched_launcher_journals_discovery_record_when_ps_has_no_matching_run(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @dataclass(kw_only=True)
    class _Runner:
        calls: list[str]
        run_finished: bool = False

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
            self.calls.append(argv[1])
            if argv[1] == "ps":
                return CommandResult(
                    exit_code=0,
                    stdout=(
                        '[{"run_id": "01OTHER", '
                        '"status": {"kind": "running"}, '
                        '"goal": "Work-item: bd-ib-other\\nRepo: /tmp/repo"}]'
                    ),
                    stderr="",
                )
            self.run_finished = True
            return CommandResult(exit_code=0, stdout="Run: 01MINE\n", stderr="")

    @dataclass(kw_only=True)
    class _Thread:
        target: Callable[[], None]
        name: str
        runner: _Runner
        daemon: bool = False
        alive_checks: int = 0

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            self.alive_checks += 1
            return not self.runner.run_finished and self.alive_checks < 3

        def join(self, timeout: float | None = None) -> None:
            _ = timeout
            self.target()

    def _thread(*, target: Callable[[], None], name: str) -> _Thread:
        return _Thread(target=target, name=name, runner=runner)

    runner = _Runner(calls=[])
    journal = _Journal(records=[])
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    assert result.abandoned_run_id is None
    assert "ps" in runner.calls
    assert "rm" not in runner.calls
    # The 11-day blind spot this test pins: a poll that discovers no matching
    # run used to `continue` with ZERO output, so a total watchdog outage was
    # indistinguishable from a healthy run. Every poll now leaves a record.
    assert journal.records == [
        {
            "work_item_id": "bd-ib-queued",
            "stage": "watchdog-discovery-poll",
            "matched": False,
            "reason": "work-item-id-mismatch",
            "ps_exit_code": 0,
            "ps_row_count": 1,
            "work_item_row_count": 0,
            "unattributed_row_count": 0,
            "status_kinds": [],
            "run_id": None,
            "status_kind": None,
        }
    ]


def test_watched_launcher_continues_when_item_status_lookup_fails(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(target=target, name=name, runner=runner)

    def _unreachable_store(*, path: StoreConfig) -> list[WorkItem]:
        _ = path
        raise BeadsConnectionError(detail="connection refused")

    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])
    _write_livespec_config(repo=tmp_path)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "read_work_items", _unreachable_store)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    assert result.abandoned_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_continues_when_item_is_absent_from_configured_store(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _thread(*, target: Callable[[], None], name: str) -> _QueuedThread:
        return _QueuedThread(target=target, name=name, runner=runner)

    runner = _QueuedRunner(calls=[], rm_calls=[])
    journal = _Journal(records=[])
    reader = Mock(
        return_value=[
            WorkItem(
                id="bd-ib-other",
                type="task",
                status="done",
                title="done",
                description="done",
                origin="freeform",
                gap_id=None,
                rank="a0",
                assignee=None,
                depends_on=(),
                captured_at="2026-08-16T00:00:00Z",
                resolution=None,
                reason=None,
                audit=None,
                superseded_by=None,
            )
        ]
    )
    _write_livespec_config(repo=tmp_path)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _thread)
    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "read_work_items", reader)
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-queued",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(sleep=lambda _seconds: None, clock=lambda: 0.0).launch(
        plan=plan,
        runner=runner,
        journal=journal,
    )

    assert result.abandoned_run_id is None
    assert runner.rm_calls == []


def _write_livespec_config(*, repo: Path) -> None:
    _ = repo.joinpath(".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {
              "prefix": "bd-ib",
              "tenant": "test-tenant",
              "fake": true
            }
          }
        }
        """,
        encoding="utf-8",
    )

"""The launch-side phases join the pre-launch CPU profile."""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher as launcher_module,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_run as run_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_prelaunch_cpu as cpu_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCpuProfile,
    drive_tree_cpu_seconds,
    ignore_prelaunch_checkpoint,
)


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id="bd-ib-5d5aue",
        branch="feat/bd-ib-5d5aue",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example.test",
        fabro_factory_dev_token=None,
        janitor=(),
        janitor_checkout=repo / "janitor",
        janitor_core_checkout=repo / "janitor-core",
        janitor_core_repo_url="https://example.test/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=0,
        merge_on_review_cap_outcome="succeeded",
    )


def _stat_line(*, pid: int, comm: str, ppid: int, ticks: tuple[int, int, int, int]) -> str:
    utime, stime, cutime, cstime = ticks
    return (
        f"{pid} ({comm}) S {ppid} 0 0 0 0 0 0 0 0 0 "
        f"{utime} {stime} {cutime} {cstime} 20 0 1 0 0 0 0\n"
    )


def test_process_tree_cpu_sums_a_fixture_tree_and_excludes_an_unrelated_process(
    tmp_path: Path,
) -> None:
    rows = {
        100: _stat_line(pid=100, comm="drive", ppid=1, ticks=(100, 50, 25, 25)),
        101: _stat_line(pid=101, comm="fabro", ppid=100, ticks=(10, 10, 0, 0)),
        102: _stat_line(pid=102, comm="git", ppid=101, ticks=(200, 0, 0, 0)),
        103: _stat_line(pid=103, comm="unrelated", ppid=1, ticks=(999, 999, 999, 999)),
    }
    for pid, line in rows.items():
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(line, encoding="utf-8")

    seconds = cpu_module.process_tree_cpu_seconds(root=tmp_path, pid=100, clock_ticks=100)

    assert seconds == 4.2


def test_the_live_drive_tree_cpu_reader_is_nonnegative_and_non_decreasing() -> None:
    first = drive_tree_cpu_seconds()
    second = drive_tree_cpu_seconds()

    assert isinstance(first, float)
    assert isinstance(second, float)
    assert 0.0 <= first <= second


def test_a_caller_with_no_profile_ignores_the_checkpoint() -> None:
    assert ignore_prelaunch_checkpoint(name="anything") is None


def test_every_launch_phase_has_a_row_before_the_run_is_submitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def checkpoint(*, name: str) -> None:
        events.append(name)

    class _StopError(Exception):
        pass

    class _Port:
        def run(self, **_: object) -> object:
            events.append("run-submitted")
            return SimpleNamespace(
                command=CommandResult(exit_code=0, stdout="", stderr=""), run_id="r"
            )

    def watch(_self: object, *, thread: threading.Thread, **_: object) -> None:
        thread.join()
        raise _StopError

    monkeypatch.setattr(launcher_module, "run_fabro_factory_auth_login", lambda **_: None)
    monkeypatch.setattr(launcher_module, "fabro_port_for_plan", lambda **_: _Port())
    monkeypatch.setattr(launcher_module, "release_pass_snapshot", lambda: None)
    monkeypatch.setattr(launcher_module, "dispatch_fabro_run_inputs", lambda **_: {})
    monkeypatch.setattr(launcher_module, "dispatch_run_label_pairs", lambda **_: ())
    monkeypatch.setattr(launcher_module.WatchedFabroLauncher, "_watch", watch)
    anything: Any = object()

    with pytest.raises(_StopError):
        _ = launcher_module.WatchedFabroLauncher(prelaunch_checkpoint=checkpoint).launch(
            plan=_plan(repo=tmp_path), runner=anything, journal=anything
        )

    assert events == [
        "launch-factory-auth",
        "fabro-port",
        "release-pass-snapshot",
        "run-submitted",
    ]


@pytest.mark.parametrize(
    ("failing", "rows"),
    [
        ("run_fabro_factory_auth_login", ["launch-factory-auth"]),
        ("fabro_port_for_plan", ["launch-factory-auth", "fabro-port"]),
        ("release_pass_snapshot", ["launch-factory-auth", "fabro-port", "release-pass-snapshot"]),
    ],
)
def test_a_launch_phase_that_raises_still_closes_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str, rows: list[str]
) -> None:
    events: list[str] = []

    def checkpoint(*, name: str) -> None:
        events.append(name)

    def boom(**_: object) -> object:
        raise RuntimeError(failing)

    monkeypatch.setattr(launcher_module, "run_fabro_factory_auth_login", lambda **_: None)
    monkeypatch.setattr(launcher_module, "fabro_port_for_plan", lambda **_: object())
    monkeypatch.setattr(launcher_module, "release_pass_snapshot", lambda: None)
    monkeypatch.setattr(launcher_module, failing, boom)
    anything: Any = object()

    with pytest.raises(RuntimeError, match=failing):
        _ = launcher_module.WatchedFabroLauncher(prelaunch_checkpoint=checkpoint).launch(
            plan=_plan(repo=tmp_path), runner=anything, journal=anything
        )

    assert events == rows


def test_the_vault_release_takes_no_checkpoint_of_its_own() -> None:
    released: list[str] = []
    checkpoint = Mock()

    launcher = launcher_module.WatchedFabroLauncher(
        prelaunch_checkpoint=checkpoint,
        on_worker_running=lambda: released.append("released"),
    )

    launcher._notify_worker_running()  # noqa: SLF001 - the exact boundary under test.

    assert released == ["released"]
    checkpoint.assert_not_called()


def test_the_dispatch_span_is_a_phase_boundary_before_the_engine_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def checkpoint(*, name: str) -> None:
        events.append(name)

    monkeypatch.setattr(run_module, "emit_dispatch_span", lambda **_: events.append("span"))
    monkeypatch.setattr(run_module, "dispatch_spans_path", lambda **_: tmp_path / "spans.jsonl")
    monkeypatch.setattr(run_module, "heartbeat_path", lambda **_: tmp_path / "beat.jsonl")
    monkeypatch.setattr(run_module, "revoke_proof_credentials", lambda **_: None)
    outcome = DispatchOutcome(
        work_item_id="bd-ib-5d5aue",
        status="green",
        stage="fabro-run",
        pr_number=42,
        merge_sha="abc123",
        detail="done",
        fabro_run_id="01RUN",
    )

    def run_dispatch(**_: object) -> DispatchOutcome:
        events.append("engine")
        return outcome

    def launcher_type(**kwargs: Any) -> Any:
        events.append("launcher" if kwargs["prelaunch_checkpoint"] is checkpoint else "wrong")
        return object()

    _ = run_module.run_dispatch_with_watchdog(
        context=run_module.DispatchRunContext(
            args=argparse.Namespace(poll_attempts=1, poll_interval_seconds=0.0),
            repo=tmp_path,
            plan=_plan(repo=tmp_path),
            journal=JournalFile(path=tmp_path / "journal.jsonl"),
            overlay_file=tmp_path / "overlay.toml",
            token_supplier=lambda: "token",
            dispatch_id="dispatch-7",
            prelaunch_checkpoint=checkpoint,
        ),
        run_dispatch_func=run_dispatch,
        fabro_launcher_type=launcher_type,
    )

    assert events == ["span", "dispatch-span", "launcher", "engine"]


def test_a_profile_checkpoint_journals_the_delta_from_an_injected_cpu_reader() -> None:
    records: list[dict[str, object]] = []
    readings = iter((4.25, 6.75))

    class _Journal:
        def append(self, *, record: dict[str, object]) -> None:
            records.append(record)

    profile = PrelaunchCpuProfile(
        journal=_Journal(),
        work_item_id="bd-ib-5d5aue",
        dispatch_id="dispatch-7",
        cpu_seconds=lambda: next(readings),
    )
    profile.checkpoint(name="spin")

    assert records == [
        {
            "stage": "pre-launch-cpu",
            "work_item_id": "bd-ib-5d5aue",
            "dispatch_id": "dispatch-7",
            "phase": "spin",
            "cpu_seconds": 2.5,
        }
    ]


def test_for_drive_uses_the_drive_tree_cpu_reader_for_each_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, object]] = []
    readings = iter((0.0, 0.0, 0.0))

    class _Journal:
        def append(self, *, record: dict[str, object]) -> None:
            records.append(record)

    def drive_cpu_reader() -> float:
        return next(readings)

    monkeypatch.setattr(cpu_module, "drive_tree_cpu_seconds", drive_cpu_reader)
    profile = cpu_module.PrelaunchCpuProfile.for_drive(
        journal=_Journal(), work_item_id="bd-ib-5d5aue", dispatch_id="dispatch-7"
    )
    profile.checkpoint(name="first")
    profile.checkpoint(name="second")

    assert profile.cpu_seconds is cpu_module.drive_tree_cpu_seconds
    assert records == [
        {
            "stage": "pre-launch-cpu",
            "work_item_id": "bd-ib-5d5aue",
            "dispatch_id": "dispatch-7",
            "phase": "first",
            "cpu_seconds": 0.0,
        },
        {
            "stage": "pre-launch-cpu",
            "work_item_id": "bd-ib-5d5aue",
            "dispatch_id": "dispatch-7",
            "phase": "second",
            "cpu_seconds": 0.0,
        },
    ]

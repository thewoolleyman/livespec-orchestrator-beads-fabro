"""CPU accounting for the work a drive spends before it launches Fabro."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_pre_dispatch_wall as wall_module,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu"
_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_prelaunch_cpu.py"
)


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_each_completed_prelaunch_phase_is_journalled_with_its_drive_tree_cpu() -> None:
    """The row is phase-specific, so the next host profile can locate regressions."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE)
    journal = _Journal()
    samples = iter((17.25, 19.75))
    profile = module.PrelaunchCpuProfile(
        journal=journal,
        work_item_id="bd-ib-5d5aue",
        dispatch_id="dispatch-7",
        cpu_seconds=lambda: next(samples),
    )

    result = profile.phase(name="record-dispatch", action=lambda: "recorded")

    assert result == "recorded"
    assert journal.records == [
        {
            "stage": "pre-launch-cpu",
            "work_item_id": "bd-ib-5d5aue",
            "dispatch_id": "dispatch-7",
            "phase": "record-dispatch",
            "cpu_seconds": 2.5,
        }
    ]


def test_the_pre_admission_wall_accepts_a_cpu_checkpoint() -> None:
    """The profile includes the expensive pre-admission refusal sequence."""
    parameters = inspect.signature(wall_module.pre_dispatch_wall_exit).parameters

    assert "prelaunch_checkpoint" in parameters


def _stat_line(*, pid: int, comm: str, ppid: int, ticks: tuple[int, int, int, int]) -> str:
    utime, stime, cutime, cstime = ticks
    return (
        f"{pid} ({comm}) S {ppid} 0 0 0 0 0 0 0 0 0 "
        f"{utime} {stime} {cutime} {cstime} 20 0 1 0 0 0 0\n"
    )


def test_process_tree_cpu_counts_live_descendants_that_os_times_cannot_see(
    tmp_path: Path,
) -> None:
    """A live `fabro run` child is invisible to `os.times()` until it is reaped."""
    module = importlib.import_module(_MODULE)
    rows = {
        100: _stat_line(pid=100, comm="drive", ppid=1, ticks=(100, 50, 25, 25)),
        101: _stat_line(pid=101, comm="fa) bro", ppid=100, ticks=(10, 10, 0, 0)),
        102: _stat_line(pid=102, comm="git", ppid=101, ticks=(200, 0, 0, 0)),
        103: _stat_line(pid=103, comm="unrelated", ppid=1, ticks=(999, 999, 999, 999)),
    }
    for pid, line in rows.items():
        (tmp_path / str(pid)).mkdir()
        _ = (tmp_path / str(pid) / "stat").write_text(line, encoding="utf-8")
    (tmp_path / "self").mkdir()
    (tmp_path / "104").mkdir()

    seconds = module.process_tree_cpu_seconds(root=tmp_path, pid=100, clock_ticks=100)

    assert seconds == 4.2


def test_a_launch_profile_holds_its_rows_until_the_dispatched_item_is_named() -> None:
    """Phases that close before the drive knows its item are not lost."""
    module = importlib.import_module(_MODULE)
    journal = _Journal()
    samples = iter((1.5, 4.0, 4.75))
    profile = module.PrelaunchCpuProfile(
        dispatch_id="dispatch-9",
        cpu_seconds=lambda: next(samples),
        baseline_cpu_seconds=0.0,
    )

    profile.checkpoint(name="drive-startup")
    profile.checkpoint(name="ledger-prepare")

    assert journal.records == []

    profile.bind(journal=journal, work_item_id="bd-ib-5d5aue")
    profile.checkpoint(name="admission")

    assert [
        (record["phase"], record["cpu_seconds"], record["work_item_id"], record["dispatch_id"])
        for record in journal.records
    ] == [
        ("drive-startup", 1.5, "bd-ib-5d5aue", "dispatch-9"),
        ("ledger-prepare", 2.5, "bd-ib-5d5aue", "dispatch-9"),
        ("admission", 0.75, "bd-ib-5d5aue", "dispatch-9"),
    ]
    assert all(record["stage"] == "pre-launch-cpu" for record in journal.records)


def test_a_held_row_keeps_the_time_its_phase_closed() -> None:
    """A row flushed at bind must not read as if its phase had just run."""
    module = importlib.import_module(_MODULE)
    journal = _Journal()
    samples = iter((1.0,))
    profile = module.PrelaunchCpuProfile(
        dispatch_id="dispatch-9",
        cpu_seconds=lambda: next(samples),
        baseline_cpu_seconds=0.0,
    )

    profile.checkpoint(name="drive-startup")
    profile.bind(journal=journal, work_item_id="bd-ib-5d5aue")

    assert isinstance(journal.records[0]["at"], str)
    assert journal.records[0]["at"].endswith("Z")


def test_the_drive_launch_profile_charges_startup_from_zero_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first row covers everything the drive spent before the profile existed."""
    module = importlib.import_module(_MODULE)
    monkeypatch.setattr(module, "drive_tree_cpu_seconds", lambda: 3.25)
    journal = _Journal()

    profile = module.PrelaunchCpuProfile.for_drive_launch(dispatch_id="dispatch-3")
    profile.bind(journal=journal, work_item_id="bd-ib-5d5aue")

    assert [(record["phase"], record["cpu_seconds"]) for record in journal.records] == [
        ("drive-startup", 3.25)
    ]
    assert journal.records[0]["dispatch_id"] == "dispatch-3"


def test_a_forked_profile_restates_every_row_so_far_under_its_own_dispatch() -> None:
    """A later dispatch in a wave still shows the phases it waited behind."""
    module = importlib.import_module(_MODULE)
    journal = _Journal()
    later = _Journal()
    samples = iter((2.0, 5.0, 6.0, 9.0, 9.5))
    profile = module.PrelaunchCpuProfile(
        dispatch_id="dispatch-1",
        cpu_seconds=lambda: next(samples),
        baseline_cpu_seconds=0.0,
    )
    profile.checkpoint(name="drive-startup")
    profile.bind(journal=journal, work_item_id="a-1")
    profile.checkpoint(name="admission")

    forked = profile.fork(dispatch_id="dispatch-2")
    forked.bind(journal=later, work_item_id="b-2")
    forked.checkpoint(name="record-dispatch")

    assert [(row["dispatch_id"], row["work_item_id"], row["phase"]) for row in later.records] == [
        ("dispatch-2", "b-2", "drive-startup"),
        ("dispatch-2", "b-2", "admission"),
        ("dispatch-2", "b-2", "record-dispatch"),
    ]
    assert {row["dispatch_id"] for row in journal.records} == {"dispatch-1"}

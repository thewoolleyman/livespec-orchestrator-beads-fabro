"""CPU accounting for the work a drive spends before it launches Fabro."""

from __future__ import annotations

import importlib
from pathlib import Path

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
        (tmp_path / str(pid) / "stat").write_text(line, encoding="utf-8")
    (tmp_path / "self").mkdir()
    (tmp_path / "104").mkdir()

    seconds = module.process_tree_cpu_seconds(root=tmp_path, pid=100, clock_ticks=100)

    assert seconds == 4.2

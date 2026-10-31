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

"""Startup and refusal outcomes for pre-launch step attribution."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_pre_dispatch_wall as wall_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCpuProfile,
)


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_startup_and_refusal_steps_are_closed_with_attribution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Both endpoints that withhold submission have complete journal intervals."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu"
    )
    monkeypatch.setattr(module, "drive_tree_cpu_seconds", lambda: 1.0)
    monkeypatch.setattr(module, "drive_process_age_seconds", lambda: 6.5, raising=False)
    startup_journal = _Journal()
    startup = module.PrelaunchCpuProfile.for_drive_launch(dispatch_id="dispatch-startup")
    startup.bind(journal=startup_journal, work_item_id="bd-ib-n4kj4y")
    startup_steps = [row for row in startup_journal.records if row["stage"] == "pre-launch-step"]
    assert [(row["event"], row["step"]) for row in startup_steps] == [
        ("start", "drive-startup"),
        ("end", "drive-startup"),
    ]
    assert startup_steps[-1]["elapsed_seconds"] == 6.5

    journal = _Journal()
    ticks = iter((0.0, 2.0))
    profile = PrelaunchCpuProfile(
        journal=journal,
        work_item_id="bd-ib-n4kj4y",
        dispatch_id="dispatch-refusal",
        cpu_seconds=lambda: 0.0,
        clock=lambda: next(ticks),
    )
    monkeypatch.setattr(
        wall_module,
        "_refusing_sequence",
        lambda **_: [(lambda: "factory unsafe", 7, True, "factory-safety-screen")],
    )
    assert (
        wall_module.pre_dispatch_wall_exit(
            args=argparse.Namespace(),
            repo=Path(),
            items=[],
            journal=JournalFile(path=tmp_path / "journal.jsonl"),
            prelaunch_checkpoint=profile.checkpoint,
        )
        == 7
    )
    assert "factory unsafe" in capsys.readouterr().err
    assert journal.records[-1]["outcome"] == "refused"

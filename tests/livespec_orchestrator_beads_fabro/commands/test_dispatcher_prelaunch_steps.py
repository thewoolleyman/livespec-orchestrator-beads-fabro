"""Every pre-launch step journals a start and an end, so no interval goes unattributed."""

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

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu"
_STAGE = "pre-launch-step"


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def steps(self) -> list[dict[str, object]]:
        return [
            {key: value for key, value in record.items() if key != "at"}
            for record in self.records
            if record.get("stage") == _STAGE
        ]


def _profile(*, journal: _Journal | None, clock: list[float]) -> PrelaunchCpuProfile:
    samples = iter(clock)
    return PrelaunchCpuProfile(
        journal=journal,
        work_item_id="bd-ib-n4kj4y" if journal is not None else None,
        dispatch_id="dispatch-7",
        cpu_seconds=lambda: 0.0,
        clock=lambda: next(samples),
    )


def test_a_completed_step_journals_a_start_and_an_end_naming_item_elapsed_and_outcome() -> None:
    journal = _Journal()
    profile = _profile(journal=journal, clock=[10.0, 12.5])

    result = profile.phase(name="record-dispatch", action=lambda: "recorded")

    assert result == "recorded"
    assert journal.steps() == [
        {
            "stage": _STAGE,
            "event": "start",
            "step": "record-dispatch",
            "work_item_id": "bd-ib-n4kj4y",
            "dispatch_id": "dispatch-7",
            "pass_id": "dispatch-7",
        },
        {
            "stage": _STAGE,
            "event": "end",
            "step": "record-dispatch",
            "work_item_id": "bd-ib-n4kj4y",
            "dispatch_id": "dispatch-7",
            "pass_id": "dispatch-7",
            "elapsed_seconds": 2.5,
            "outcome": "completed",
        },
    ]
    assert [record["stage"] for record in journal.records] == [
        _STAGE,
        "pre-launch-cpu",
        _STAGE,
    ]


def test_a_step_that_raises_still_journals_its_end_before_the_error_propagates() -> None:
    journal = _Journal()
    profile = _profile(journal=journal, clock=[1.0, 4.0])

    def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        profile.phase(name="github-app-auth", action=boom)

    end = journal.steps()[-1]
    assert (end["event"], end["step"], end["outcome"], end["elapsed_seconds"]) == (
        "end",
        "github-app-auth",
        "failed",
        3.0,
    )


def test_a_step_that_refuses_journals_a_refused_end() -> None:
    module = importlib.import_module(_MODULE)
    journal = _Journal()
    profile = _profile(journal=journal, clock=[0.0, 1.0])

    with module.prelaunch_phase(checkpoint=profile.checkpoint, name="ledger-check") as step:
        step.outcome = "refused"

    assert journal.steps()[-1]["outcome"] == "refused"


def test_the_pre_dispatch_wall_journals_the_end_of_a_refusing_row_before_it_returns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    journal = _Journal()
    profile = _profile(journal=journal, clock=[0.0, 2.0])
    monkeypatch.setattr(
        wall_module,
        "_refusing_sequence",
        lambda **_: [(lambda: "factory unsafe", 7, True, "factory-safety-screen")],
    )

    exit_code = wall_module.pre_dispatch_wall_exit(
        args=argparse.Namespace(),
        repo=Path(),
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        prelaunch_checkpoint=profile.checkpoint,
    )

    assert exit_code == 7
    assert "factory unsafe" in capsys.readouterr().err
    end = journal.steps()[-1]
    assert (end["event"], end["step"], end["outcome"]) == (
        "end",
        "factory-safety-screen",
        "refused",
    )


def test_steps_closed_before_the_item_is_known_are_journaled_under_it_at_bind() -> None:
    journal = _Journal()
    profile = _profile(journal=None, clock=[5.0, 6.0])

    profile.phase(name="ledger-prepare", action=lambda: None)
    assert journal.records == []
    profile.bind(journal=journal, work_item_id="bd-ib-n4kj4y")

    assert [(row["event"], row["step"], row["work_item_id"]) for row in journal.steps()] == [
        ("start", "ledger-prepare", "bd-ib-n4kj4y"),
        ("end", "ledger-prepare", "bd-ib-n4kj4y"),
    ]
    assert {row["pass_id"] for row in journal.steps()} == {"dispatch-7"}


def test_a_forked_profile_restates_the_steps_under_its_own_dispatch_and_the_same_pass() -> None:
    journal = _Journal()
    later = _Journal()
    profile = _profile(journal=None, clock=[0.0, 1.0, 2.0, 3.0])
    profile.phase(name="ledger-prepare", action=lambda: None)

    forked = profile.fork(dispatch_id="dispatch-8")
    forked.bind(journal=later, work_item_id="b-2")
    profile.bind(journal=journal, work_item_id="a-1")

    assert [(row["dispatch_id"], row["pass_id"], row["work_item_id"]) for row in later.steps()] == [
        ("dispatch-8", "dispatch-7", "b-2"),
        ("dispatch-8", "dispatch-7", "b-2"),
    ]


def test_the_drive_launch_profile_journals_process_startup_as_a_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(_MODULE)
    monkeypatch.setattr(module, "drive_tree_cpu_seconds", lambda: 1.0)
    monkeypatch.setattr(module, "drive_process_age_seconds", lambda: 6.5, raising=False)
    journal = _Journal()

    profile = module.PrelaunchCpuProfile.for_drive_launch(dispatch_id="dispatch-3")
    profile.bind(journal=journal, work_item_id="bd-ib-n4kj4y")

    start, end = journal.records[0], journal.records[-1]
    assert [(row["event"], row["step"]) for row in journal.steps()] == [
        ("start", "drive-startup"),
        ("end", "drive-startup"),
    ]
    assert end["elapsed_seconds"] == 6.5
    assert str(start["at"]) < str(end["at"])


def test_process_age_is_the_uptime_less_the_process_start_time(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE)
    (tmp_path / "uptime").write_text("1000.50 3000.00\n", encoding="utf-8")
    (tmp_path / "42").mkdir()
    fields = ["S", "1", *["0"] * 17, "99000", "0"]
    (tmp_path / "42" / "stat").write_text(f"42 (python) {' '.join(fields)}\n", encoding="utf-8")

    age = module.process_age_seconds(root=tmp_path, pid=42, clock_ticks=100)

    assert age == 10.5
    assert module.process_age_seconds(root=tmp_path, pid=43, clock_ticks=100) == 0.0

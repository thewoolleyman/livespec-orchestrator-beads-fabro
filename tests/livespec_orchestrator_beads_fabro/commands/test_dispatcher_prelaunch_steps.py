"""Pre-launch step boundaries in the dispatch journal."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    PrelaunchCpuProfile,
)


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_a_completed_prelaunch_step_journals_start_and_end_with_its_attribution() -> None:
    """A named item has an interval, outcome, and elapsed seconds for each step."""
    journal = _Journal()
    samples = iter((10.0, 12.5))
    profile = PrelaunchCpuProfile(
        journal=journal,
        work_item_id="bd-ib-n4kj4y",
        dispatch_id="dispatch-7",
        cpu_seconds=lambda: 0.0,
        clock=lambda: next(samples),
    )

    assert profile.phase(name="record-dispatch", action=lambda: "recorded") == "recorded"

    assert [record for record in journal.records if record["stage"] == "pre-launch-step"] == [
        {
            "stage": "pre-launch-step",
            "event": "start",
            "step": "record-dispatch",
            "work_item_id": "bd-ib-n4kj4y",
            "dispatch_id": "dispatch-7",
            "pass_id": "dispatch-7",
        },
        {
            "stage": "pre-launch-step",
            "event": "end",
            "step": "record-dispatch",
            "work_item_id": "bd-ib-n4kj4y",
            "dispatch_id": "dispatch-7",
            "pass_id": "dispatch-7",
            "elapsed_seconds": 2.5,
            "outcome": "completed",
        },
    ]

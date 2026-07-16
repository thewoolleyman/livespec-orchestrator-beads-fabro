"""Tests for the dispatcher's extracted cost-gate stage."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FakeRunner:
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        self.calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _host_only_refused(*, work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route this item",
    )


def test_cost_gate_after_verdict_skips_probe_when_no_green_outcome() -> None:
    journal = _RecordingJournal()
    runner = _FakeRunner()

    cost_gate_after_verdict(
        args=argparse.Namespace(items=None, fabro_bin="fabro"),
        repo=Path("/repo"),
        outcomes=[_host_only_refused(work_item_id="item-host")],
        journal=journal,
        runner=runner,
    )

    assert runner.calls == []
    assert journal.records == []

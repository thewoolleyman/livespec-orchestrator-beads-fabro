"""Coverage for helpers in the Red test module without changing its bytes."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


class _Journal(Protocol):
    records: list[dict[str, object]]

    def append(self, *, record: dict[str, object]) -> None:
        """Append one test record."""
        ...


class _Runner(Protocol):
    calls: list[dict[str, object]]

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        """Record one fake command invocation."""
        ...


def test_red_module_helpers_record_invocations() -> None:
    namespace = runpy.run_path(
        "tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_cost_gate.py"
    )
    journal_factory = cast(Callable[[], _Journal], namespace["_RecordingJournal"])
    runner_factory = cast(Callable[[], _Runner], namespace["_FakeRunner"])

    journal = journal_factory()
    journal.append(record={"stage": "covered"})

    runner = runner_factory()
    result = runner.run(argv=["fabro", "ps"], cwd=Path("/repo"), timeout_seconds=1.0)

    assert journal.records == [{"stage": "covered"}]
    assert runner.calls == [{"argv": ["fabro", "ps"], "cwd": Path("/repo"), "timeout_seconds": 1.0}]
    assert result == CommandResult(exit_code=0, stdout="[]", stderr="")

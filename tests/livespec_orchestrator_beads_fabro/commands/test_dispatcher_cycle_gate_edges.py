"""The two gate arms a well-formed dispatch cannot reach.

Beside `test_dispatcher_cycle_gate`, which covers both evaluation boundaries on a
readable repository, this file covers the arms that exist for the states that
arrive AFTER the pre-dispatch wall has already passed: a `.livespec.jsonc` that
became unreadable mid-run, and a terminal reading whose own inputs fault.

Each is asserted for its DIRECTION rather than merely for not crashing. The
unreadable policy must leave the gate OBSERVATIONAL — naming the fault and
manufacturing no breach — because refusing there would attribute a configuration
edit to the slice as a non-convergence bounce. And the terminal reading must
fail OPEN, journaling its own `-error` stage: the verdict is already final by the
time it runs, so a probe fault there has no decision left to influence and must
not crash a dispatch that has finished.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_gate import (
    RUNTIME_CONVERGENCE_STAGE,
    TERMINAL_BOUNDARY,
    pre_merge_runtime_gate,
    record_dispatch_runtime_convergence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"


@dataclass(kw_only=True)
class _ForgeRunner:
    stdout: str = ""
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert isinstance(cwd, Path)
        assert env is None
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _item() -> WorkItem:
    return WorkItem(  # pyright: ignore[reportArgumentType]
        id="bd-ib-z2y4ca",
        type="feature",
        status="active",
        title="Feed per-cycle progress signals into the bounce",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a5",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n",
    )


def _payload() -> str:
    return json.dumps(
        {
            "commits": [
                {
                    "oid": "0" * 40,
                    "messageHeadline": "feat(pkg): one assertion",
                    "messageBody": (
                        "TDD-Red-Test-File-Checksum: sha256:one\n"
                        "TDD-Red-Captured-At: 2026-10-01T10:00:00Z\n"
                        f"Factory-Run-Id: {_DISPATCH_ID}\n"
                        "TDD-Green-Verified-At: 2026-10-01T10:00:40Z\n"
                    ),
                }
            ]
        }
    )


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_config_unreadable_mid_run_names_the_fault_and_breaches_nothing(
    tmp_path: Path,
) -> None:
    (tmp_path / ".livespec.jsonc").write_text("{ not valid jsonc", encoding="utf-8")
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    gate = pre_merge_runtime_gate(
        repo=tmp_path,
        item=_item(),
        dispatch_id=_DISPATCH_ID,
        fix_loop_count=0,
        fix_loop_cap=3,
        journal=journal,
        runner=_ForgeRunner(stdout=_payload()),
    )

    assert gate(pr_number=4242, run_id="run-1") is None
    record = next(
        record
        for record in _records(path=journal.path)
        if record["stage"] == RUNTIME_CONVERGENCE_STAGE
    )
    unresolved = record["ceiling_policy_unresolved"]
    assert isinstance(unresolved, str)
    # The EXCEPTION TYPE is named, not just the fact of a fault: the two unusable
    # shapes have different remedies and the wall tells them apart by this.
    assert unresolved.startswith("LivespecConfigUnreadableError")
    assert record["bounce_contributors"] == []


def test_a_faulting_terminal_reading_journals_its_error_stage_and_returns_none(
    tmp_path: Path,
) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    # An `args` carrying no journal attribute faults inside the reading the way a
    # missing runtime input would; the supervisor must absorb it.
    taken = record_dispatch_runtime_convergence(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-z2y4ca",
            status="green",
            stage="done",
            pr_number=4242,
            merge_sha="0" * 40,
            detail="merged",
        ),
        journal=journal,
    )

    assert taken is None
    record = next(
        record
        for record in _records(path=journal.path)
        if record["stage"] == f"{RUNTIME_CONVERGENCE_STAGE}-error"
    )
    assert record["boundary"] == TERMINAL_BOUNDARY
    assert record["reason"] == "AttributeError"
    assert record["work_item_id"] == "bd-ib-z2y4ca"

"""The two boundaries at which the runtime cycle observations are evaluated.

Scenario 165 requires the retained cycle observations to be evaluated at the
pre-merge convergence verification boundary AND when recording a terminal
non-converged run. Both land here, through ONE evaluation that journals one
`runtime-convergence` record naming which boundary produced it — so the two
readings cannot diverge in how they measure, only in when they are taken.

A pre-merge breach returns a non-convergence terminal, which is what routes the
item through the SANCTIONED backlog bounce rather than a second disposition of
its own: the detail carries the non-converged sentinel the existing bounce
predicate already recognises.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_gate"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_gate.py"
)

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _ForgeRunner:
    stdout: str = ""
    exit_code: int = 0
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
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def _item(*, criteria: str = "- One assertion.\n- Two assertions.\n") -> WorkItem:
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
        acceptance_criteria=criteria,
    )


def _config(*, repo: Path, ceiling: str = "") -> None:
    (repo / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "dispatcher": {\n'
        '      "wip_cap": 3'
        f"{ceiling}\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )


def _payload(*, elapsed_green: str = "2026-10-01T10:04:10Z") -> str:
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
                        f"TDD-Green-Verified-At: {elapsed_green}\n"
                    ),
                }
            ]
        }
    )


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_pre_merge_boundary_journals_its_reading_and_passes_a_healthy_run(
    tmp_path: Path,
) -> None:
    module = _module()
    _config(repo=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    gate = module.pre_merge_runtime_gate(
        repo=tmp_path,
        item=_item(),
        dispatch_id=_DISPATCH_ID,
        fix_loop_count=0,
        fix_loop_cap=3,
        journal=journal,
        runner=_ForgeRunner(stdout=_payload()),
    )
    terminal = gate(pr_number=4242, run_id="run-1")

    assert terminal is None
    records = [
        record
        for record in _records(path=journal.path)
        if record["stage"] == module.RUNTIME_CONVERGENCE_STAGE
    ]
    assert len(records) == 1
    assert records[0]["boundary"] == module.PRE_MERGE_BOUNDARY
    assert records[0]["completed_cycle_count"] == 1
    assert records[0]["effective_assertion_count"] == 2
    assert records[0]["bounce_contributors"] == []


def test_a_pre_merge_ceiling_breach_returns_a_sanctioned_non_convergence_terminal(
    tmp_path: Path,
) -> None:
    module = _module()
    _config(repo=tmp_path, ceiling=',\n      "adopted_cycle_duration_seconds_ceiling": 10')
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    gate = module.pre_merge_runtime_gate(
        repo=tmp_path,
        item=_item(),
        dispatch_id=_DISPATCH_ID,
        fix_loop_count=0,
        fix_loop_cap=3,
        journal=journal,
        runner=_ForgeRunner(stdout=_payload()),
    )
    terminal = gate(pr_number=4242, run_id="run-1")

    assert terminal is not None
    assert terminal.status == "failed"
    assert NON_CONVERGED_MARKER in terminal.detail
    assert "adopted_cycle_duration_seconds_ceiling" in terminal.detail
    assert terminal.fabro_run_id == "run-1"
    record = next(
        record
        for record in _records(path=journal.path)
        if record["stage"] == module.RUNTIME_CONVERGENCE_STAGE
    )
    assert record["bounce_contributors"] == [module.CYCLE_CEILING_CONTRIBUTOR]


def test_the_terminal_boundary_records_its_own_reading(tmp_path: Path) -> None:
    module = _module()
    _config(repo=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    verdict = module.record_terminal_runtime_convergence(
        repo=tmp_path,
        item=_item(
            criteria=(
                "- The first assertion holds.\n"
                "- The second assertion holds.\n"
                "- The third assertion holds.\n"
            )
        ),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        fix_loop_count=3,
        fix_loop_cap=3,
        journal=journal,
        runner=_ForgeRunner(stdout=_payload()),
    )

    assert verdict.progress_deficit
    record = next(
        record
        for record in _records(path=journal.path)
        if record["stage"] == module.RUNTIME_CONVERGENCE_STAGE
    )
    assert record["boundary"] == module.TERMINAL_BOUNDARY
    assert record["completed_cycle_count"] == 1
    assert record["effective_assertion_count"] == 3
    assert record["bounce_contributors"] == [module.PROGRESS_DEFICIT_CONTRIBUTOR]
    assert record["fix_loop_cap"] == 3


def test_invalid_committed_policy_leaves_the_gate_observational(tmp_path: Path) -> None:
    module = _module()
    _config(repo=tmp_path, ceiling=',\n      "adopted_cycle_product_lloc_ceiling": 0')
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    gate = module.pre_merge_runtime_gate(
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
        if record["stage"] == module.RUNTIME_CONVERGENCE_STAGE
    )
    assert record["ceiling_policy_unresolved"] is not None
    assert record["bounce_contributors"] == []

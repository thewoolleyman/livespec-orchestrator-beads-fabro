"""The admission gate refuses a repeated flat history before any claim.

Covers `SPECIFICATION/contracts.md` section "Across-dispatch required-result
progress" and Scenario 151.  The module is reached through `importlib` inside
the test body so the Red commit fails on a genuine assertion
(`module_path.is_file()` / the missing refusal) and not at collection.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_gate"
_ITEM = "bd-ib-flat"


class _Factories:
    """A reader answering only from the factory a run was recorded on."""

    def __init__(self, *, records: dict[tuple[str, str], object]) -> None:
        self.records = records
        self.reads: list[tuple[str, str]] = []

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.reads.append((factory, run_id))
        return self.records.get((factory, run_id))


def _failed_run(*, succeeded: tuple[str, ...], failed: str, cause: str) -> object:
    outcomes: dict[str, object] = {node: {"status": "succeeded"} for node in succeeded}
    outcomes[failed] = {
        "status": "failed",
        "failure": {"category": "deterministic", "signature": f"{failed}|x", "causes": [cause]},
    }
    return [{"status": {"kind": "failed"}, "checkpoint": {"node_outcomes": outcomes}}]


def _journal(*, repo: Path, stamps: list[tuple[str, str]]) -> JournalFile:
    journal = JournalFile(path=repo / "journal.jsonl")
    for run_id, factory in stamps:
        journal.append(
            record={
                "stage": "dispatch-run-stamp",
                "work_item_id": _ITEM,
                "run_id": run_id,
                "dispatch_factory": factory,
            }
        )
    return journal


def _repo(*, tmp_path: Path, limit: int | None) -> Path:
    dispatcher: dict[str, object] = {} if limit is None else {"redispatch_no_progress_limit": limit}
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="Flat candidate",
        description="## Definition of Done\n\n- One assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def test_repeated_flat_attempts_refuse_before_claim_naming_their_evidence(tmp_path: Path) -> None:
    """Two attributable terminals at the baseline's mark refuse, from their own factories."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_redispatch_gate.py"
    )
    assert module_path.is_file()
    gate = importlib.import_module(_MODULE)
    repo = _repo(tmp_path=tmp_path, limit=2)
    journal = _journal(repo=repo, stamps=[("RUN1", "petri"), ("RUN2", "hp"), ("RUN3", "petri")])
    factories = _Factories(
        records={
            ("petri", "RUN1"): _failed_run(succeeded=("dod_gate",), failed="implement", cause="a"),
            ("hp", "RUN2"): _failed_run(succeeded=("dod_gate",), failed="implement", cause="b"),
            ("petri", "RUN3"): _failed_run(succeeded=("dod_gate",), failed="implement", cause="c"),
        }
    )

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, reader=factories
    )

    assert refusal is not None
    assert refusal.status == "failed"
    assert refusal.stage == "redispatch-no-progress"
    assert "RUN2" in refusal.detail
    assert "RUN3" in refusal.detail
    assert "RUN1" not in refusal.detail
    assert "factory hp" in refusal.detail
    assert "dod_gate" in refusal.detail
    assert ("hp", "RUN2") in factories.reads

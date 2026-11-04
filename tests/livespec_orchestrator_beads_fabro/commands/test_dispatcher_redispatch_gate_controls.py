"""Controls that keep the redispatch gate from being a universal refusal.

Each refusal case of Scenario 151 has a sibling here in which the same shape of
history is admitted: a normal success, advancing attempts, host faults, an
active run.  Without them a gate that refused every item with any history would
satisfy the refusal case equally well.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_gate import (
    RECOVERY_CONSUMED_STAGE,
    record_redispatch_recovery,
    redispatch_progress_refusal,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-ctrl"


class _Factories:
    def __init__(self, *, records: dict[tuple[str, str], object]) -> None:
        self.records = records
        self.reads: list[tuple[str, str]] = []

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.reads.append((factory, run_id))
        return self.records.get((factory, run_id))


def _run(
    *, kind: str, done: tuple[str, ...] = (), failed: str | None = None, cause: str = "x"
) -> object:
    outcomes: dict[str, object] = {node: {"status": "succeeded"} for node in done}
    if failed is not None:
        outcomes[failed] = {"status": "failed", "failure": {"causes": [cause]}}
    return [{"status": {"kind": kind}, "checkpoint": {"node_outcomes": outcomes}}]


def _flat(*, cause: str = "boom") -> object:
    return _run(kind="failed", done=("dod_gate",), failed="implement", cause=cause)


def _repo(*, tmp_path: Path, limit: object = 2, workflows: dict[str, str] | None = None) -> Path:
    dispatcher: dict[str, object] = {} if limit is None else {"redispatch_no_progress_limit": limit}
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    for name, text in (workflows or {}).items():
        graph = tmp_path / ".fabro" / "workflows" / name / "workflow.fabro"
        graph.parent.mkdir(parents=True)
        _ = graph.write_text(text, encoding="utf-8")
    return tmp_path


def _journal(*, repo: Path, runs: list[tuple[str, str | None]]) -> JournalFile:
    journal = JournalFile(path=repo / "journal.jsonl")
    for run_id, factory in runs:
        record: dict[str, object] = {"stage": "dispatch-run-stamp", "work_item_id": _ITEM}
        record["run_id"] = run_id
        if factory is not None:
            record["dispatch_factory"] = factory
        journal.append(record=record)
    return journal


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="Control candidate",
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


def _gate(
    *, repo: Path, journal: JournalFile, records: dict[tuple[str, str], object]
) -> tuple[object, _Factories]:
    factories = _Factories(records=records)
    outcome = redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, reader=factories
    )
    return outcome, factories


def test_an_item_with_no_earlier_run_is_admitted_without_reading_the_limit(tmp_path: Path) -> None:
    """No history means nothing to count, so even a missing limit does not refuse."""
    repo = _repo(tmp_path=tmp_path, limit=None)
    outcome, factories = _gate(repo=repo, journal=_journal(repo=repo, runs=[]), records={})
    assert outcome is None
    assert factories.reads == []


def test_a_normal_successful_history_is_admitted(tmp_path: Path) -> None:
    """Failures followed by a success that reached the end are not a flat history."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = _journal(repo=repo, runs=[("A", "petri"), ("B", "petri"), ("C", "petri")])
    records = {
        ("petri", "A"): _flat(),
        ("petri", "B"): _flat(),
        ("petri", "C"): _run(kind="succeeded", done=("dod_gate", "implement", "janitor", "pr")),
    }
    outcome, _ = _gate(repo=repo, journal=journal, records=records)
    assert outcome is None


def test_advancing_attempts_reset_the_count(tmp_path: Path) -> None:
    """Each attempt reaching a deeper milestone than before is progress."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = _journal(repo=repo, runs=[("A", "petri"), ("B", "petri"), ("C", "petri")])
    records = {
        ("petri", "A"): _run(kind="failed", done=("dod_gate",), failed="implement"),
        ("petri", "B"): _run(kind="failed", done=("dod_gate", "implement"), failed="janitor"),
        ("petri", "C"): _run(
            kind="failed", done=("dod_gate", "implement", "janitor"), failed="review"
        ),
    }
    outcome, _ = _gate(repo=repo, journal=journal, records=records)
    assert outcome is None


def test_host_failures_neither_increment_nor_reset_and_active_runs_do_not_count(
    tmp_path: Path,
) -> None:
    """Only the attributable flat attempt counts, so a limit of two is not reached."""
    repo = _repo(tmp_path=tmp_path, limit=2)
    journal = _journal(
        repo=repo,
        runs=[("A", "petri"), ("H1", "petri"), ("F", "petri"), ("H2", "petri"), ("L", "petri")],
    )
    host = _run(kind="failed", done=("dod_gate",), failed="implement", cause="database is locked")
    records = {
        ("petri", "A"): _flat(),
        ("petri", "H1"): host,
        ("petri", "F"): _flat(),
        ("petri", "H2"): _run(kind="canceled"),
        ("petri", "L"): _run(kind="running"),
    }
    outcome, _ = _gate(repo=repo, journal=journal, records=records)
    assert outcome is None


def test_a_missing_or_invalid_limit_refuses_with_a_configuration_diagnostic(tmp_path: Path) -> None:
    """With history to count, an absent or invalid limit is a refusal naming the key."""
    for limit in (None, 0, True):
        repo = _repo_dir(tmp_path=tmp_path, name=str(limit), limit=limit)
        journal = _journal(repo=repo, runs=[("A", "petri")])
        outcome, factories = _gate(repo=repo, journal=journal, records={("petri", "A"): _flat()})
        assert getattr(outcome, "stage", None) == "configuration"
        assert "redispatch_no_progress_limit" in getattr(outcome, "detail", "")
        assert factories.reads == []


def _repo_dir(*, tmp_path: Path, name: str, limit: object) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    return _repo(tmp_path=repo, limit=limit)


def test_evidence_is_read_only_from_the_recorded_factory(tmp_path: Path) -> None:
    """A run recorded on `hp` is unknown when only another factory answers for it."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = _journal(repo=repo, runs=[("A", "hp"), ("B", None)])
    records = {("default", "A"): _flat(), ("default", "B"): _flat()}
    outcome, factories = _gate(repo=repo, journal=journal, records=records)
    assert getattr(outcome, "stage", None) == "redispatch-diagnosis"
    assert "A" in getattr(outcome, "detail", "")
    assert factories.reads == [("hp", "A")]


def test_incomparable_workflow_variants_require_a_diagnosis(tmp_path: Path) -> None:
    """A target-local graph with another topology is not comparable to the bundle."""
    repo = _repo(
        tmp_path=tmp_path,
        limit=1,
        workflows={"custom": "digraph G { start; start -> only; }"},
    )
    journal = JournalFile(path=repo / "journal.jsonl")
    for run_id, dispatch_id, name in (("A", "D1", "implement-work-item"), ("B", "D2", "custom")):
        journal.append(
            record={"stage": "dispatch-id", "dispatch_id": dispatch_id, "workflow_name": name}
        )
        journal.append(
            record={
                "stage": "dispatch-run-stamp",
                "work_item_id": _ITEM,
                "run_id": run_id,
                "dispatch_id": dispatch_id,
                "dispatch_factory": "petri",
            }
        )
    outcome, _ = _gate(
        repo=repo, journal=journal, records={("petri", "A"): _flat(), ("petri", "B"): _flat()}
    )
    assert getattr(outcome, "stage", None) == "redispatch-diagnosis"
    assert "incomparable workflow" in getattr(outcome, "detail", "")


def test_a_recovery_authorizes_one_dispatch_and_cannot_be_replayed(tmp_path: Path) -> None:
    """The consumed attempt id refuses the same recovery the next time."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = _journal(repo=repo, runs=[("A", "petri"), ("B", "petri")])
    records = {("petri", "A"): _flat(), ("petri", "B"): _flat()}
    refused, _ = _gate(repo=repo, journal=journal, records=records)
    assert getattr(refused, "stage", None) == "redispatch-no-progress"
    record_redispatch_recovery(
        journal=journal,
        work_item_id=_ITEM,
        attempt_id="recovery-1",
        prior_run_ids=["B"],
        diagnosis="the implement prompt omitted the fixture",
        operation="dispatch --item bd-ib-ctrl",
        execution_evidence="receipt-1",
    )
    admitted, _ = _gate(repo=repo, journal=journal, records=records)
    replayed, _ = _gate(repo=repo, journal=journal, records=records)
    assert admitted is None
    assert getattr(replayed, "stage", None) == "redispatch-no-progress"
    consumed = [
        line
        for line in (repo / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        if RECOVERY_CONSUMED_STAGE in line
    ]
    assert len(consumed) == 1
    assert "recovery-1" in consumed[0]


def test_a_recovery_that_omits_its_evidence_is_a_diagnosis_not_an_admission(tmp_path: Path) -> None:
    """A prose-only record, or one naming the wrong history, authorizes nothing."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = _journal(repo=repo, runs=[("A", "petri"), ("B", "petri")])
    records = {("petri", "A"): _flat(), ("petri", "B"): _flat()}
    journal.append(
        record={"stage": "redispatch-recovery-attempt", "work_item_id": _ITEM, "attempt_id": "r"}
    )
    outcome, _ = _gate(repo=repo, journal=journal, records=records)
    assert getattr(outcome, "stage", None) == "redispatch-diagnosis"
    assert "measured diagnosis" in getattr(outcome, "detail", "")


def test_a_workflow_with_no_readable_graph_cannot_be_compared(tmp_path: Path) -> None:
    """With no graph anywhere, milestones cannot be ordered and a diagnosis is required."""
    repo = _repo(tmp_path=tmp_path, limit=1)
    journal = JournalFile(path=repo / "journal.jsonl")
    for run_id in ("A", "B"):
        journal.append(
            record={"stage": "dispatch-id", "dispatch_id": run_id, "workflow_name": "no-such-flow"}
        )
        journal.append(
            record={
                "stage": "dispatch-run-stamp",
                "work_item_id": _ITEM,
                "run_id": run_id,
                "dispatch_id": run_id,
                "dispatch_factory": "petri",
            }
        )
    outcome, _ = _gate(
        repo=repo, journal=journal, records={("petri", "A"): _flat(), ("petri", "B"): _flat()}
    )
    assert getattr(outcome, "stage", None) == "redispatch-diagnosis"

"""Pre-claim across-dispatch refusal, read off the item's recorded run history.

Scenario 151: the admission gate reads the item's journaled terminals, grades
each run's milestone from the factory the run was recorded on, and refuses the
NEXT claim once the committed `dispatcher.redispatch_no_progress_limit` of
item-attributable terminals failed to advance the prior high-water mark.
Normal histories are controls: they must be admitted, or the rule is a
universal refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_admission import (
    redispatch_progress_refusal,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-sample"
_GRAPH = """digraph G {
  start [shape=Mdiamond]
  implement [shape=parallelogram]
  review [shape=parallelogram]
  pr [shape=parallelogram]
  done [shape=Msquare]
  start -> implement
  implement -> review
  review -> pr
  pr -> done
}
"""
_PARTIAL = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: the implement turn left work incomplete"


class _Runs:
    """Fake factory reader keyed by (factory, run id); records every read."""

    def __init__(self, *, succeeded: dict[str, tuple[str, ...]]) -> None:
        self.succeeded = succeeded
        self.reads: list[tuple[str, str]] = []

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        self.reads.append((factory, run_id))
        nodes = self.succeeded.get(run_id)
        if nodes is None:
            return None
        return [
            {
                "run_id": run_id,
                "status": {"kind": "failed"},
                "checkpoint": {
                    "node_outcomes": {node: {"status": "succeeded"} for node in nodes},
                },
            }
        ]


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="Sample",
        description="## Definition of Done\n\n- It works.\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _repo(*, tmp_path: Path, limit: object | None = 2) -> Path:
    dispatcher: dict[str, object] = {} if limit is None else {"redispatch_no_progress_limit": limit}
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8"
    )
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return tmp_path


def _terminal(*, journal: JournalFile, run_id: str, detail: str = _PARTIAL) -> None:
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM_ID,
                "status": "blocked",
                "stage": "fabro-run",
                "fabro_run_id": run_id,
                "fabro_factory_name": "petri",
                "detail": detail,
                "needs_human_kind": "stage-failure",
                "needs_human_stages": ["implement"],
            },
        }
    )


def _journal(*, tmp_path: Path, runs: tuple[str, ...]) -> JournalFile:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    for run_id in runs:
        _terminal(journal=journal, run_id=run_id)
    return journal


def _flat_runs() -> _Runs:
    return _Runs(succeeded={"01A": ("start", "implement"), "01B": ("start",), "01C": ("start",)})


def test_flat_history_refuses_before_claim_naming_runs_causes_and_milestone(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    runs = _flat_runs()

    refusal = redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=runs
    )

    assert refusal is not None
    assert refusal.status == "failed"
    assert refusal.stage == "redispatch-no-progress"
    assert "01B" in refusal.detail
    assert "01C" in refusal.detail
    assert "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in refusal.detail
    assert "implement" in refusal.detail
    assert ("petri", "01A") in runs.reads


def test_advancing_history_is_admitted(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    runs = _Runs(
        succeeded={
            "01A": ("start",),
            "01B": ("start", "implement"),
            "01C": ("start", "implement", "review"),
        }
    )

    assert (
        redispatch_progress_refusal(repo=repo, item=_item(), journal=journal, factory_runs=runs)
        is None
    )


def test_item_without_history_is_admitted_without_reading_a_factory(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, limit=None)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    runs = _Runs(succeeded={})

    assert (
        redispatch_progress_refusal(repo=repo, item=_item(), journal=journal, factory_runs=runs)
        is None
    )
    assert runs.reads == []


def test_missing_limit_is_a_configuration_refusal_before_claim(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, limit=None)
    journal = _journal(tmp_path=tmp_path, runs=("01A",))

    refusal = redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat_runs()
    )

    assert refusal is not None
    assert refusal.stage == "configuration"
    assert "redispatch_no_progress_limit" in refusal.detail


def test_host_failures_neither_count_nor_reset(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _terminal(journal=journal, run_id="01A")
    _terminal(journal=journal, run_id="01B")
    _terminal(journal=journal, run_id="01C", detail="database is locked")

    assert (
        redispatch_progress_refusal(
            repo=repo, item=_item(), journal=journal, factory_runs=_flat_runs()
        )
        is None
    )


def _recovery(*, journal: JournalFile, attempt_id: str) -> None:
    journal.append(
        record={
            "stage": "redispatch-recovery",
            "work_item_id": _ITEM_ID,
            "attempt_id": attempt_id,
            "prior_run_ids": ["01B", "01C"],
            "diagnosis": "implement turn ran out of budget before committing",
            "operation": f"impl:{_ITEM_ID}",
            "execution_evidence": "resume from the preserved tree 0a5b4507",
        }
    )


def test_typed_recovery_authorizes_one_dispatch_and_cannot_be_replayed(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    runs = _flat_runs()
    _recovery(journal=journal, attempt_id="recovery-1")

    admitted = redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=runs
    )
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "d2"})
    replayed = redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=runs
    )

    assert admitted is None
    assert replayed is not None
    assert replayed.stage == "redispatch-no-progress"

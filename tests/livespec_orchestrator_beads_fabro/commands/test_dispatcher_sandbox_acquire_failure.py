"""The post-checkpoint sandbox-acquire terminal has its own durable account."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
    needs_human_cause_body,
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_acquire_failure import (
    SANDBOX_ACQUIRE_FAILURE,
    sandbox_acquire_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_CAUSE = "could not acquire the environment: sandbox acquire failed: pod timed out"


def _plan() -> DispatchPlan:
    return cast(DispatchPlan, SimpleNamespace(work_item_id="bd-ib-iydhau"))


def _inspect(*, payload: object, status_kind: str = "failed") -> FabroInspectResult:
    return cast(
        FabroInspectResult,
        SimpleNamespace(payload=payload, status_kind=status_kind),
    )


def _failure(*, cause: object = _CAUSE) -> object:
    return SimpleNamespace(cause=cause, category="deterministic", signature=None)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-iydhau",
        type="bug",
        status="active",
        title="Rest sandbox acquisition failures at needs-human",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


def _write_config(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )


@dataclass
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_sandbox_acquire_failure_carries_the_checkpoint_and_engine_detail() -> None:
    """The mapped ending supplies the data its durable comment must preserve."""
    outcome = sandbox_acquire_failure_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(),
        run_id="01M6G7Z3NVMA2JREGHV670QEDR",
        inspect=_inspect(
            payload={
                "status": {"reason": "workflow_error"},
                "conclusion": {"final_git_commit_sha": "f65923ed177e5d73332f7f3ece04ffb70f077984"},
            }
        ),
        failure=_failure(),
    )

    assert outcome is not None
    assert outcome.needs_human_kind == SANDBOX_ACQUIRE_FAILURE
    assert outcome.final_git_commit_sha == "f65923ed177e5d73332f7f3ece04ffb70f077984"
    assert outcome.fabro_failure_cause == _CAUSE

    body = needs_human_cause_body(
        outcome=replace(outcome, needs_human_preservation="preserved on the run ref"),
        preserve_by_reference="stages/055-implement@1/diff.patch (3759 bytes)",
    )

    assert f"engine failure detail: {_CAUSE}" in body
    assert "final checkpoint commit: f65923ed177e5d73332f7f3ece04ffb70f077984" in body
    assert "preserve-by-reference artifact: stages/055-implement@1/diff.patch (3759 bytes)" in body
    assert "preservation: preserved on the run ref" in body


def test_only_the_measured_workflow_error_is_reclassified() -> None:
    """Malformed, non-terminal, and unrelated failures retain their old route."""
    assert (
        sandbox_acquire_failure_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(),
            run_id=None,
            inspect=None,
            failure=_failure(),
        )
        is None
    )
    assert (
        sandbox_acquire_failure_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(),
            run_id=None,
            inspect=_inspect(payload=[]),
            failure=_failure(),
        )
        is None
    )
    assert (
        sandbox_acquire_failure_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(),
            run_id=None,
            inspect=_inspect(payload={"status": {"reason": "cancelled"}}),
            failure=_failure(),
        )
        is None
    )
    assert (
        sandbox_acquire_failure_outcome(
            outcome_type=DispatchOutcome,
            plan=_plan(),
            run_id=None,
            inspect=_inspect(payload={"status": {"reason": "workflow_error"}}),
            failure=_failure(cause="ordinary stage failure"),
        )
        is None
    )


def test_a_missing_checkpoint_stays_absent() -> None:
    """The account never invents a seed when the engine recorded none."""
    outcome = sandbox_acquire_failure_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(),
        run_id=None,
        inspect=_inspect(payload={"status": {"reason": "workflow_error"}}),
        failure=_failure(),
    )

    assert outcome is not None
    assert outcome.final_git_commit_sha is None


def test_absent_sandbox_evidence_is_not_invented() -> None:
    """Only engine-recorded evidence is carried into the durable account."""
    body = needs_human_cause_body(
        outcome=DispatchOutcome(
            work_item_id="bd-ib-iydhau",
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="sandbox acquisition failed",
            needs_human_kind=SANDBOX_ACQUIRE_FAILURE,
        )
    )

    assert "engine failure detail:" not in body
    assert "final checkpoint commit:" not in body
    assert "preserve-by-reference artifact:" not in body


def test_durable_cause_repeats_the_preserve_by_reference_artifact(tmp_path: Path) -> None:
    """The comment survives the run with its exact seed and ending category."""
    _write_config(repo=tmp_path)
    append_work_item(path=_config(), item=_item())
    run_id = "01M6G7Z3NVMA2JREGHV670QEDR"
    pointer = f"livespec-preserve-by-reference\nrun id: {run_id}\nstages/055-implement@1/diff.patch"
    append_work_item_comment(path=_config(), work_item_id=_item().id, body=pointer)
    outcome = sandbox_acquire_failure_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(),
        run_id=run_id,
        inspect=_inspect(
            payload={
                "status": {"reason": "workflow_error"},
                "conclusion": {"final_git_commit_sha": "f65923ed177e5d73332f7f3ece04ffb70f077984"},
            }
        ),
        failure=_failure(),
    )
    assert outcome is not None
    journal = _Journal()

    record_needs_human_cause(
        repo=tmp_path,
        item=_item(),
        outcome=outcome,
        journal=cast(JournalFile, journal),
    )

    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_item().id)
        if NEEDS_HUMAN_CAUSE_MARKER in comment.text
    ]
    assert len(bodies) == 1
    assert f"ending: {SANDBOX_ACQUIRE_FAILURE}" in bodies[0]
    assert f"engine failure detail: {_CAUSE}" in bodies[0]
    assert "final checkpoint commit: f65923ed177e5d73332f7f3ece04ffb70f077984" in bodies[0]
    assert f"preserve-by-reference artifact: {pointer}" in bodies[0]
    assert journal.records == [
        {
            "stage": "needs-human-cause-record",
            "work_item_id": _item().id,
            "needs_human_kind": SANDBOX_ACQUIRE_FAILURE,
        }
    ]

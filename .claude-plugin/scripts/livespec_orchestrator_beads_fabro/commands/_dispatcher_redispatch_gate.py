"""Refuse the next claim of an item whose recent attempts made no progress.

The pre-claim half of `SPECIFICATION/contracts.md` section "Across-dispatch
required-result progress".  It joins four things the sibling modules own: the
committed limit (`_dispatcher_redispatch_limit`), the item's stamped runs read
from the factories they were launched on (`_dispatcher_redispatch_history`),
the typed recovery records the journal carries, and the pure decision
(`_dispatcher_redispatch_progress`).  An item with no stamped run has no
history to count, so it is admitted without consulting the limit.

A recovery authorization is consumed in the same step that admits the item: the
`redispatch-recovery-consumed` row is what makes its attempt id unusable a
second time, and no recovery carries a deadline field, so it cannot postpone
the item's original required-result deadline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    RecordedRun,
    RunReader,
    WorkflowOrder,
    completed_attempt,
    recorded_runs,
    workflow_order,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_limit import (
    resolve_redispatch_no_progress_limit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchProgressRefusal,
    RedispatchRecovery,
    redispatch_progress_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RECOVERY_ATTEMPT_STAGE",
    "RECOVERY_CONSUMED_STAGE",
    "record_redispatch_recovery",
    "redispatch_progress_refusal",
]

RECOVERY_ATTEMPT_STAGE = "redispatch-recovery-attempt"
RECOVERY_CONSUMED_STAGE = "redispatch-recovery-consumed"
_UNCLAIMED = "No claim was taken and no Fabro run was created."
_DEFAULT_WORKFLOW = "implement-work-item"
_BUNDLED_WORKFLOWS = Path(__file__).resolve().parents[3] / ".fabro" / "workflows"


def record_redispatch_recovery(  # noqa: PLR0913 -- kw-only; each argument is one field of the typed recovery record.
    *,
    journal: JournalFile,
    work_item_id: str,
    attempt_id: str,
    prior_run_ids: Sequence[str],
    diagnosis: str,
    operation: str,
    execution_evidence: str,
) -> None:
    """Journal one typed causal recovery attempt for an item's refused history."""
    journal.append(
        record={
            "stage": RECOVERY_ATTEMPT_STAGE,
            "work_item_id": work_item_id,
            "attempt_id": attempt_id,
            "prior_run_ids": list(prior_run_ids),
            "diagnosis": diagnosis,
            "operation": operation,
            "execution_evidence": execution_evidence,
        }
    )


def redispatch_progress_refusal(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    reader: RunReader | None = None,
) -> DispatchOutcome | None:
    """The refusal the item's attempt history earns before a claim, or `None` to admit."""
    records = read_journal_records(journal_path=getattr(journal, "path", None))
    runs = recorded_runs(records=records, work_item_id=item.id)
    if not runs:
        return None
    resolved = resolve_redispatch_no_progress_limit(cwd=repo)
    if not is_successful(resolved):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="configuration",
            detail=unsafe_perform_io(resolved.failure()).detail,
        )
    run_reader = reader if reader is not None else FactoryRunReader(repo=repo, journal=journal)
    orders: dict[str, WorkflowOrder | None] = {}
    attempts: list[CompletedAttempt] = []
    for run in runs:
        name = run.workflow_name or _DEFAULT_WORKFLOW
        if name not in orders:
            orders[name] = workflow_order(graph_text=_graph_text(repo=repo, name=name))
        payload = (
            run_reader.inspect_payload(factory=run.factory, run_id=run.run_id)
            if run.factory is not None
            else None
        )
        attempts.append(completed_attempt(run=run, payload=payload, order=orders[name]))
    decision = redispatch_progress_decision(
        limit=unsafe_perform_io(resolved.unwrap()),
        attempts=tuple(attempts),
        recovery=_latest_recovery(records=records, work_item_id=item.id),
        consumed_recovery_attempt_ids=_consumed(records=records, work_item_id=item.id),
    )
    if decision.diagnosis is not None:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="redispatch-diagnosis",
            detail=_diagnosis_detail(item_id=item.id, diagnosis=decision.diagnosis),
        )
    if decision.refusal is not None:
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="redispatch-no-progress",
            detail=_refusal_detail(item_id=item.id, refusal=decision.refusal, runs=runs),
        )
    if decision.authorized_recovery_attempt_id is not None:
        journal.append(
            record={
                "stage": RECOVERY_CONSUMED_STAGE,
                "work_item_id": item.id,
                "attempt_id": decision.authorized_recovery_attempt_id,
            }
        )
    return None


def _diagnosis_detail(*, item_id: str, diagnosis: str) -> str:
    return f"{item_id}: attempt history needs a diagnosis first: {diagnosis}. {_UNCLAIMED}"


def _refusal_detail(
    *, item_id: str, refusal: RedispatchProgressRefusal, runs: tuple[RecordedRun, ...]
) -> str:
    factories = {run.run_id: run.factory for run in runs}
    attempts = "; ".join(
        f"run {run_id} on factory {factories.get(run_id) or 'unrecorded'}: {cause}"
        for run_id, cause in zip(refusal.run_ids, refusal.causes, strict=True)
    )
    return (
        f"{item_id}: {len(refusal.run_ids)} consecutive item-attributable attempts did not "
        f"advance the progress high-water mark (last successful milestone: "
        f"{refusal.high_water_milestone}): {attempts}. A fresh typed causal recovery attempt "
        f"naming these run ids, a measured diagnosis, an executable operation and its "
        f"execution evidence authorizes exactly one more dispatch; the original "
        f"required-result deadline is unchanged. {_UNCLAIMED}"
    )


def _graph_text(*, repo: Path, name: str) -> str | None:
    for root in (repo / ".fabro" / "workflows", _BUNDLED_WORKFLOWS):
        path = root / name / "workflow.fabro"
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def _latest_recovery(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> RedispatchRecovery | None:
    latest: RedispatchRecovery | None = None
    for record in records:
        if (
            record.get("stage") != RECOVERY_ATTEMPT_STAGE
            or record.get("work_item_id") != work_item_id
        ):
            continue
        prior = record.get("prior_run_ids")
        latest = RedispatchRecovery(
            attempt_id=_text(value=record.get("attempt_id")),
            prior_run_ids=tuple(str(run) for run in cast("list[object]", prior))
            if isinstance(prior, list)
            else (),
            diagnosis=_text(value=record.get("diagnosis")),
            operation=_text(value=record.get("operation")),
            execution_evidence=_text(value=record.get("execution_evidence")),
        )
    return latest


def _consumed(*, records: Sequence[Mapping[str, object]], work_item_id: str) -> frozenset[str]:
    return frozenset(
        attempt_id
        for record in records
        if record.get("stage") == RECOVERY_CONSUMED_STAGE
        and record.get("work_item_id") == work_item_id
        and isinstance(attempt_id := record.get("attempt_id"), str)
    )


def _text(*, value: object) -> str:
    return value if isinstance(value, str) else ""

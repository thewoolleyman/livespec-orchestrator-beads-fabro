"""The pre-claim across-dispatch progress refusal.

`SPECIFICATION/contracts.md` section "Across-dispatch required-result progress"
requires admission, BEFORE claiming a work-item, to compare each completed
attempt with the high-water mark established before it, and to refuse the next
dispatch once the committed `dispatcher.redispatch_no_progress_limit` of
item-attributable terminals failed to advance it.

This module is the seam between that pure rule (`_dispatcher_redispatch_progress`)
and the evidence it needs. The attempts are the item's journaled terminals, so
the history is the same one an operator reads; each item-attributable terminal's
milestone is then read from the factory that run was RECORDED on, never from the
local default server. A terminal that is not item-attributable is never read at
all: it can neither increment nor reset, so its milestone decides nothing.

THE GRADE IS PURE AND THE REFUSAL JOURNALS. Recovery routing grades the same
question to keep a refused item from being routed, and a second journaled
outcome from that earlier look would report one refusal twice.

An item with no journaled terminal has no comparison to make, so it reads
neither configuration nor a factory: a first dispatch is never refused by this
gate. A missing or invalid limit is reported as a `configuration` refusal the
moment a comparison is owed, because an implicit count would be a policy nobody
committed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    JournaledTerminal,
    consumed_recovery_attempt_ids,
    item_terminals,
    newest_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_milestones import (
    committed_node_ranks,
    run_milestone,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchProgressDecision,
    redispatch_progress_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CONFIGURATION_STAGE",
    "DIAGNOSIS_STAGE",
    "NO_PROGRESS_STAGE",
    "RedispatchGrade",
    "RunInspector",
    "grade_redispatch_progress",
    "redispatch_progress_refusal",
]

CONFIGURATION_STAGE = "configuration"
NO_PROGRESS_STAGE = "redispatch-no-progress"
DIAGNOSIS_STAGE = "redispatch-diagnosis-required"
_LIMIT_KEY = "redispatch_no_progress_limit"
_POLICY = f"dispatcher.{_LIMIT_KEY}"


class RunInspector(Protocol):
    """The one factory read the gate spends: a run's record, from its own factory."""

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        """Return the run's inspect record, or `None` when it cannot be read."""
        ...


@dataclass(frozen=True, kw_only=True)
class RedispatchGrade:
    """Why the next claim is refused: the refusal's stage and its operator-facing text."""

    stage: str
    detail: str


def redispatch_progress_refusal(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    factory_runs: RunInspector | None = None,
) -> DispatchOutcome | None:
    """The journaled pre-claim refusal for this item, or `None` to admit it."""
    grade = grade_redispatch_progress(
        repo=repo,
        work_item_id=item.id,
        records=read_journal_records(journal_path=getattr(journal, "path", None)),
        factory_runs=factory_runs,
    )
    if grade is None:
        return None
    return failed_dispatch_outcome(
        journal=journal, work_item_id=item.id, stage=grade.stage, detail=grade.detail
    )


def grade_redispatch_progress(
    *,
    repo: Path,
    work_item_id: str,
    records: Sequence[Mapping[str, object]],
    factory_runs: RunInspector | None = None,
) -> RedispatchGrade | None:
    """Grade one item's recorded history against the committed limit, without writing."""
    terminals = item_terminals(records=records, work_item_id=work_item_id)
    if not terminals:
        return None
    limit = _limit(repo=repo)
    if isinstance(limit, str):
        return RedispatchGrade(stage=CONFIGURATION_STAGE, detail=limit)
    reader = FactoryRunReader(repo=repo) if factory_runs is None else factory_runs
    ranks = committed_node_ranks(repo=repo)
    attempts = tuple(
        _attempt(terminal=terminal, reader=reader, ranks=ranks) for terminal in terminals
    )
    recovery = newest_recovery(records=records, work_item_id=work_item_id)
    consumed = consumed_recovery_attempt_ids(records=records, work_item_id=work_item_id)
    decision = redispatch_progress_decision(
        limit=limit,
        attempts=attempts,
        recovery=None if recovery is not None and recovery.attempt_id in consumed else recovery,
        consumed_recovery_attempt_ids=consumed,
    )
    return _grade(work_item_id=work_item_id, limit=limit, decision=decision, terminals=terminals)


def _limit(*, repo: Path) -> int | str:
    """The committed positive limit, or the configuration diagnostic naming what is wrong."""
    resolved = read_dispatcher_config_value(cwd=repo, key=_LIMIT_KEY)
    if not is_successful(resolved):
        return f"{_POLICY} is unreadable: {unsafe_perform_io(resolved.failure()).detail}"
    value = unsafe_perform_io(resolved.unwrap())
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return (
        f"{_POLICY} must be a positive committed integer before a re-dispatch can be graded; "
        f"got {value!r}"
    )


def _attempt(
    *, terminal: JournaledTerminal, reader: RunInspector, ranks: dict[str, int] | None
) -> CompletedAttempt:
    if terminal.item_attributable is not True:
        return CompletedAttempt(
            run_id=terminal.run_id,
            terminal_cause=terminal.cause,
            high_water_milestone="n/a",
            item_attributable=terminal.item_attributable,
        )
    milestone = (
        None
        if ranks is None
        else run_milestone(
            payload=reader.inspect_payload(factory=terminal.factory, run_id=terminal.run_id),
            ranks=ranks,
        )
    )
    if milestone is None:
        return CompletedAttempt(
            run_id=terminal.run_id,
            terminal_cause=f"{terminal.cause} (milestone unreadable on {terminal.factory})",
            high_water_milestone="unreadable",
            item_attributable=None,
        )
    return CompletedAttempt(
        run_id=terminal.run_id,
        terminal_cause=terminal.cause,
        high_water_milestone=milestone.name,
        item_attributable=True,
        workflow_identity=milestone.workflow_identity,
        high_water_order=milestone.order,
    )


def _grade(
    *,
    work_item_id: str,
    limit: int,
    decision: RedispatchProgressDecision,
    terminals: tuple[JournaledTerminal, ...],
) -> RedispatchGrade | None:
    if decision.diagnosis is not None:
        return RedispatchGrade(
            stage=DIAGNOSIS_STAGE,
            detail=(
                f"{work_item_id}: re-dispatch refused before claim, a diagnosis is required: "
                f"{decision.diagnosis}"
            ),
        )
    refusal = decision.refusal
    if refusal is None:
        return None
    factories = {terminal.run_id: terminal.factory for terminal in terminals}
    runs = "; ".join(
        f"{run_id} on {factories[run_id]}: {cause}"
        for run_id, cause in zip(refusal.run_ids, refusal.causes, strict=True)
    )
    return RedispatchGrade(
        stage=NO_PROGRESS_STAGE,
        detail=(
            f"{work_item_id}: re-dispatch refused before claim, {len(refusal.run_ids)} "
            f"item-attributable runs did not advance past the high-water milestone "
            f"{refusal.high_water_milestone!r} ({_POLICY}={limit}): {runs}. Record a typed causal "
            "recovery attempt (journal stage redispatch-recovery: attempt_id, prior_run_ids, "
            "diagnosis, operation, execution_evidence) naming these runs to authorize one new "
            "dispatch epoch; prose naming a changed approach does not."
        ),
    )

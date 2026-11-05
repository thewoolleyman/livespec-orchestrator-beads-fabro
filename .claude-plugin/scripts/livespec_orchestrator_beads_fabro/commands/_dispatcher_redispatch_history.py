"""One item's journaled terminals and typed recovery attempts, read off the dispatch journal.

`SPECIFICATION/contracts.md` section "Across-dispatch required-result progress"
compares each completed attempt with the high-water mark established before it.
The attempts are the `outcome` rows the Dispatcher journals for every terminal,
which carry the run id AND the factory name that run was recorded on, so the
milestone read that follows goes to the factory the run lived on rather than to
whichever server is the local default.

THE CAUSE IS GRADED THREE WAYS, never two. A run is host-attributable when the
Dispatcher released it (provider-limit or adapter-launch release, both journaled
with the run id), when it ended on a usage limit, or when its recorded text
carries a measured host-fault signature. It is item-attributable only on
positive evidence: a causal stage, a non-convergence marker or a workflow
failure marker. Everything else is UNKNOWN, which the progress decision turns
into a diagnosis requirement and never into a silent host failure.

THE SEQUENCE STARTS AFTER THE ITEM'S LAST GREEN TERMINAL. A merged result is the
required result, so history behind it is a different obligation and would only
make an unrelated later dispatch pay for it.

A RECOVERY ATTEMPT IS CONSUMED BY POSITION. The journal is append-only, so the
`dispatch-id` row every launch writes is the durable proof that a recovery row
before it has been spent; no counter is stored beside the rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    ADAPTER_LAUNCH_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause import (
    WORKER_EXIT_BEFORE_TERMINAL_EVENT,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import is_executable_operation

__all__: list[str] = [
    "RECOVERY_STAGE",
    "JournaledTerminal",
    "consumed_recovery_attempt_ids",
    "item_terminals",
    "newest_recovery",
]

RECOVERY_STAGE = "redispatch-recovery"

_OUTCOME_STAGE = "outcome"
_DISPATCH_ID_STAGE = "dispatch-id"
_GREEN = "green"
_RELEASE_STAGES = frozenset({PROVIDER_LIMIT_RELEASE_STAGE, ADAPTER_LAUNCH_RELEASE_STAGE})
_HOST_SIGNATURES = (
    "database is locked",
    "sandbox became unreachable",
    "the exec stream ended without an exit status",
    "fencing a recorded sandbox",
    WORKER_EXIT_BEFORE_TERMINAL_EVENT,
)
_ITEM_SIGNATURES = (NON_CONVERGED_MARKER, "LIVESPEC_IMPLEMENT_", "LIVESPEC_REVIEW_")
_CAUSE_LIMIT = 160


@dataclass(frozen=True, kw_only=True)
class JournaledTerminal:
    """One run's terminal as the Dispatcher journaled it, with its graded cause."""

    run_id: str
    factory: str
    cause: str
    item_attributable: bool | None


def item_terminals(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> tuple[JournaledTerminal, ...]:
    """The item's run terminals since its last green one, in journal order."""
    released = _released_run_ids(records=records)
    terminals: list[JournaledTerminal] = []
    for record in records:
        outcome = _outcome_of(record=record, work_item_id=work_item_id)
        if outcome is None:
            continue
        if outcome.get("status") == _GREEN:
            terminals = []
            continue
        run_id, factory = outcome.get("fabro_run_id"), outcome.get("fabro_factory_name")
        if isinstance(run_id, str) and isinstance(factory, str):
            terminals.append(
                _terminal(outcome=outcome, run_id=run_id, factory=factory, released=released)
            )
    return tuple(terminals)


def newest_recovery(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> RedispatchRecovery | None:
    """The item's newest typed recovery row; an unusable field reads as absent.

    A field that is not the shape the clause names is carried as EMPTY, so the
    progress decision reports exactly which causal field is missing rather than
    this reader inventing one. An operation outside the closed executable
    grammar is empty for the same reason: prose names no operation.
    """
    newest: Mapping[str, object] | None = None
    for record in records:
        if record.get("stage") == RECOVERY_STAGE and record.get("work_item_id") == work_item_id:
            newest = record
    if newest is None:
        return None
    operation = _text(value=newest.get("operation"))
    return RedispatchRecovery(
        attempt_id=_text(value=newest.get("attempt_id")),
        prior_run_ids=_run_ids(value=newest.get("prior_run_ids")),
        diagnosis=_text(value=newest.get("diagnosis")),
        operation=operation if is_executable_operation(operation=operation) else "",
        execution_evidence=_text(value=newest.get("execution_evidence")),
    )


def consumed_recovery_attempt_ids(
    *, records: Sequence[Mapping[str, object]], work_item_id: str
) -> frozenset[str]:
    """Attempt ids of this item's recovery rows that a later launch has spent."""
    pending: set[str] = set()
    consumed: set[str] = set()
    for record in records:
        if record.get("work_item_id") != work_item_id:
            continue
        stage = record.get("stage")
        if stage == RECOVERY_STAGE:
            pending.add(_text(value=record.get("attempt_id")))
        elif stage == _DISPATCH_ID_STAGE:
            consumed |= pending
            pending = set()
    return frozenset(consumed)


def _terminal(
    *, outcome: Mapping[str, object], run_id: str, factory: str, released: frozenset[str]
) -> JournaledTerminal:
    text = " ".join(
        value
        for value in (
            outcome.get("detail"),
            outcome.get("fabro_failure_cause"),
            outcome.get("needs_human_reason"),
        )
        if isinstance(value, str)
    )
    if run_id in released or outcome.get("provider_usage_limit") is True:
        attributable: bool | None = False
    elif any(signature in text for signature in _HOST_SIGNATURES):
        attributable = False
    elif outcome.get("needs_human_stages") or any(
        signature in text for signature in _ITEM_SIGNATURES
    ):
        attributable = True
    else:
        attributable = None
    cause = text.strip().splitlines()[0][:_CAUSE_LIMIT] if text.strip() else "no recorded cause"
    return JournaledTerminal(
        run_id=run_id, factory=factory, cause=cause, item_attributable=attributable
    )


def _released_run_ids(*, records: Sequence[Mapping[str, object]]) -> frozenset[str]:
    return frozenset(
        run_id
        for record in records
        if record.get("stage") in _RELEASE_STAGES
        and isinstance(run_id := record.get("run_id"), str)
    )


def _outcome_of(*, record: Mapping[str, object], work_item_id: str) -> Mapping[str, object] | None:
    outcome = record.get("outcome")
    if record.get("stage") != _OUTCOME_STAGE or not isinstance(outcome, Mapping):
        return None
    typed = cast("Mapping[str, object]", outcome)
    return typed if typed.get("work_item_id") == work_item_id else None


def _text(*, value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _run_ids(*, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(entry) for entry in cast("list[object]", value))

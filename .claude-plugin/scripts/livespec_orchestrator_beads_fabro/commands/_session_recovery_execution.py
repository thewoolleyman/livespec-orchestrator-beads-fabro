"""Running one sanctioned recovery command at most once, whatever arrives twice.

`contracts.md` section "Launch obligations and consumed recovery" sets the bar
and then refuses to overstate it: "Duplicate events, concurrent consumers and
restart MUST converge on one observed effect for the supported idempotent
recovery command. After an ambiguous execution crash the consumer MUST query
durable command effects before retrying, retain unobservable state if it cannot
decide, and MUST NOT claim exactly-once arbitrary shell execution."

WHY CONVERGENCE RESTS ON THE RECORDED EFFECT RATHER THAN ON THE LOCK. A lock
serializes two consumers that are both alive; it says nothing about the one that
died mid-command, which is the case that duplicates work. The recorded EFFECT is
what survives that death, so a second arrival reads it and returns it rather
than running anything — and the command is consulted only where no effect, and
no evidence that one may exist, is on the record.

WHY A `started` TRANSITION WITH NO EFFECT IS THE WHOLE AMBIGUITY. It is written
BEFORE the command runs, so it is exactly the trace a crash leaves: something
may have happened, and the record cannot say. That state routes the next pass
into the durable-effect LOOKUP instead of into the command, which is the clause's
own prescription. Writing `started` after the command would make the crash
invisible and the retry blind.

WHY AN UNOBSERVABLE LOOKUP WRITES NOTHING AND RUNS NOTHING. The natural coding
of "I asked and saw no effect" is "there is no effect, so run it", and that is
the arm where one work item gets dispatched twice. The clause says to "retain
unobservable state if it cannot decide", so the pass reports `uncertain` and
leaves the record exactly as it found it — in the state that brings the next
pass back to the same lookup.

WHY THE FENCE IS CHECKED BEFORE THE EFFECT AND BEFORE THE COMMAND. A displaced
consumer must not write, and must not run; checking its standing first makes
both structural rather than a property of the order the rest of this module
happens to take. The refusal is COUNTED through the lease surface, because a
silently dropped displacement reports a clean zero for the event an operator
most needs to see.

WHY THIS MODULE CANNOT NAME A COMMAND. The command is a protocol its caller
supplies, so there is no shell string, no interpolation and no predicate here —
the clause's "No arbitrary shell predicate/result implementation" limit holds
structurally. WHICH operation may be supplied is decided by
`_session_recovery_action`, which grades it against the sanctioned grammar
before any of this runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import (
    RecoveryEffect,
    RecoveryEffectReader,
    SanctionedCommand,
    record_recovery_effect,
    recorded_effect,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_lease import (
    FENCE_CURRENT,
    FENCE_UNCLAIMED,
    fence_state,
    record_fenced_mutation,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    APPEND_RECORDED,
    TRANSITION_STARTED,
    append_recovery_transition,
    observed_transitions,
    read_recovery_record,
    recovery_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import LockBudget

__all__: list[str] = [
    "EXECUTION_ABSENT",
    "EXECUTION_ALREADY_EXECUTED",
    "EXECUTION_EFFECT_RECOVERED",
    "EXECUTION_EXECUTED",
    "EXECUTION_FENCED",
    "EXECUTION_UNAVAILABLE",
    "EXECUTION_UNCERTAIN",
    "EXECUTION_UNCLAIMED",
    "EXECUTION_UNOBSERVABLE",
    "ExecutionOutcome",
    "ExecutionRequest",
    "execute_recovery",
]

EXECUTION_EXECUTED = "executed"
EXECUTION_ALREADY_EXECUTED = "already-executed"
EXECUTION_EFFECT_RECOVERED = "effect-recovered"
EXECUTION_UNCERTAIN = "uncertain"
EXECUTION_FENCED = "fenced"
EXECUTION_UNCLAIMED = "unclaimed"
EXECUTION_ABSENT = "absent"
EXECUTION_UNOBSERVABLE = "unobservable"
EXECUTION_UNAVAILABLE = "unavailable"


@dataclass(frozen=True, kw_only=True)
class ExecutionRequest:
    """One consumer's bid to execute one attempt, at the generation it holds.

    `consumer` and `generation` travel TOGETHER because the fence is the pair:
    a name without a generation cannot tell a current holder from the copy of
    itself that lapsed, which is the whole displacement this guards.
    """

    recovery_store_root: Path
    attempt_id: str
    consumer: str
    generation: int
    operation: str
    observed_at: float
    lock_budget: LockBudget | None = None


@dataclass(frozen=True, kw_only=True)
class ExecutionOutcome:
    """The one effect this attempt converged on, or why it converged on none."""

    state: str
    effect: RecoveryEffect | None

    @property
    def converged(self) -> bool:
        return self.effect is not None


def execute_recovery(
    *,
    request: ExecutionRequest,
    command: SanctionedCommand,
    reader: RecoveryEffectReader,
) -> ExecutionOutcome:
    """Converge one attempt on a single command effect, running it at most once."""
    loaded = read_recovery_record(
        path=recovery_record_path(
            recovery_store_root=request.recovery_store_root, attempt_id=request.attempt_id
        )
    )
    if loaded.payload is None:
        return ExecutionOutcome(
            state=EXECUTION_ABSENT if loaded.diagnostic is None else EXECUTION_UNOBSERVABLE,
            effect=None,
        )
    standing = fence_state(
        payload=loaded.payload, consumer=request.consumer, generation=request.generation
    )
    if standing != FENCE_CURRENT:
        return _refused(request=request, standing=standing)
    return _executed(request=request, payload=loaded.payload, command=command, reader=reader)


def _refused(*, request: ExecutionRequest, standing: str) -> ExecutionOutcome:
    """Refuse a consumer with no current standing, counting a displacement.

    An UNCLAIMED attempt is not a displacement — nobody took it away, this
    caller simply never claimed it — so no fenced count moves. The two are
    reported apart because the remedies differ: claim first, versus stop.
    """
    if standing == FENCE_UNCLAIMED:
        return ExecutionOutcome(state=EXECUTION_UNCLAIMED, effect=None)
    _ = record_fenced_mutation(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        lock_budget=request.lock_budget,
    )
    return ExecutionOutcome(state=EXECUTION_FENCED, effect=None)


def _executed(
    *,
    request: ExecutionRequest,
    payload: dict[str, object],
    command: SanctionedCommand,
    reader: RecoveryEffectReader,
) -> ExecutionOutcome:
    """Decide what a currently-fenced consumer owes: nothing, a lookup, or a run."""
    already = recorded_effect(payload=payload)
    if already is not None:
        return ExecutionOutcome(state=EXECUTION_ALREADY_EXECUTED, effect=already)
    if TRANSITION_STARTED in observed_transitions(payload=payload):
        observed = reader.observe(attempt_id=request.attempt_id)
        if observed is None:
            return ExecutionOutcome(state=EXECUTION_UNCERTAIN, effect=None)
        return _recorded(request=request, effect=observed, state=EXECUTION_EFFECT_RECOVERED)
    return _started(request=request, command=command)


def _started(*, request: ExecutionRequest, command: SanctionedCommand) -> ExecutionOutcome:
    """Mark the start, run the command once, and record whatever it reports."""
    status = append_recovery_transition(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        transition=TRANSITION_STARTED,
        observed_at=request.observed_at,
        detail={"operation": request.operation},
        lock_budget=request.lock_budget,
    )
    if status != APPEND_RECORDED:
        return ExecutionOutcome(state=EXECUTION_UNAVAILABLE, effect=None)
    produced = command(attempt_id=request.attempt_id, operation=request.operation)
    if produced is None:
        return ExecutionOutcome(state=EXECUTION_UNCERTAIN, effect=None)
    return _recorded(request=request, effect=produced, state=EXECUTION_EXECUTED)


def _recorded(*, request: ExecutionRequest, effect: RecoveryEffect, state: str) -> ExecutionOutcome:
    """Record one effect through the receipt surface, reporting only a real write.

    Anything other than a written receipt is `unavailable` rather than an
    execution: a lock this budget could not take and a record that vanished
    under the write have one remedy — come back — and neither may be reported
    as a command effect that converged.
    """
    written = record_recovery_effect(
        recovery_store_root=request.recovery_store_root,
        attempt_id=request.attempt_id,
        effect=effect,
        observed_at=request.observed_at,
        lock_budget=request.lock_budget,
    )
    if written is not True:
        return ExecutionOutcome(state=EXECUTION_UNAVAILABLE, effect=None)
    return ExecutionOutcome(state=state, effect=effect)

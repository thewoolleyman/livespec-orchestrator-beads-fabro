"""The result one consumer pass hands a scheduler, assembled off the attempt itself.

Split from `_session_recovery_consumer` by cohesion: that module owns the ORDER
of the pass, and this one owns what the pass REPORTS — the state vocabulary a
scheduler acts on, and the assembly that reads the obligation's own fields back
out of the record.

WHY THE OBLIGATION FIELDS ARE READ BACK RATHER THAN CARRIED FORWARD. The clause
asks a deferral to retain "the original obligation/deadline history", and the
cheap way to report that is to echo whatever the caller passed in — which would
say nothing at all, since the caller's copy cannot have been changed by a pass
that never looked at it. Reading them off the record AFTER the pass is what makes
the report evidence: a pass that had shortened the deadline would report the
shortened one.

WHY AN EXECUTION STATE THAT IS NEITHER A RUN NOR A CONVERGENCE PASSES THROUGH
VERBATIM. `uncertain`, `fenced` and `unavailable` have three different next moves
— come back and look the effect up, stop, retry the write — and a scheduler told
one failure word for all three would retry them alike. Folding them is the
natural coding and it is the one that makes an ambiguous execution look like a
transient.

WHY `None` IS RESERVED FOR AN UNREADABLE ATTEMPT. The three obligation fields are
`None` together and only when no record could be read, so a caller can tell "this
attempt has no deadline I could see" from "this attempt's deadline is X". A zero
or an empty string in their place would be a value nobody wrote.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_recovery_consumption import (
    RecoveryConsumption,
    recovery_consumption,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_effect import RecoveryEffect
from livespec_orchestrator_beads_fabro.commands._session_recovery_execution import (
    EXECUTION_ALREADY_EXECUTED,
    EXECUTION_EFFECT_RECOVERED,
    EXECUTION_EXECUTED,
)
from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    read_recovery_record,
    recovery_record_path,
)

__all__: list[str] = [
    "CONSUMER_CONVERGED",
    "CONSUMER_DEFERRED",
    "CONSUMER_EXECUTED",
    "CONSUMER_NOT_AUTHORIZED",
    "CONSUMER_UNCLAIMED",
    "ConsumerDecision",
    "ConsumerOutcome",
    "consumer_outcome",
    "consumer_state",
]

CONSUMER_EXECUTED = "executed"
CONSUMER_CONVERGED = "converged"
CONSUMER_DEFERRED = "deferred"
CONSUMER_NOT_AUTHORIZED = "not-authorized"
CONSUMER_UNCLAIMED = "unclaimed"

# The two execution states that mean one command effect stands WITHOUT this pass
# having run it. Kept apart from `executed` because "I ran it" and "somebody's
# run of it is on the record" are different facts about the same effect.
_CONVERGED_STATES: tuple[str, ...] = (EXECUTION_ALREADY_EXECUTED, EXECUTION_EFFECT_RECOVERED)


@dataclass(frozen=True, kw_only=True)
class ConsumerDecision:
    """What one pass decided, before the obligation's own fields are read back.

    A value rather than five parameters, so every arm of the pass names its
    fields explicitly: an arm that forgot one cannot silently inherit a
    positional default from its neighbour.
    """

    state: str
    barrier: str | None = None
    operation: str | None = None
    effect: RecoveryEffect | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ConsumerOutcome:
    """Everything a scheduler needs from one pass, including what it did not do."""

    state: str
    barrier: str | None
    operation: str | None
    effect: RecoveryEffect | None
    generation: int
    latency_seconds: float | None
    original_deadline: str | None
    result_epoch: int | None
    diagnostics: tuple[str, ...]

    @property
    def executed(self) -> bool:
        return self.state == CONSUMER_EXECUTED

    @property
    def deferred(self) -> bool:
        return self.state == CONSUMER_DEFERRED


def consumer_state(*, execution_state: str) -> str:
    """Map one execution state onto what the scheduler is being told."""
    if execution_state == EXECUTION_EXECUTED:
        return CONSUMER_EXECUTED
    if execution_state in _CONVERGED_STATES:
        return CONSUMER_CONVERGED
    return execution_state


def consumer_outcome(
    *,
    recovery_store_root: Path,
    attempt_id: str,
    decision: ConsumerDecision,
    generation: int,
) -> ConsumerOutcome:
    """Assemble the outcome, reading the obligation's own fields back off the record."""
    graded = _consumption(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    return ConsumerOutcome(
        state=decision.state,
        barrier=decision.barrier,
        operation=decision.operation,
        effect=decision.effect,
        generation=generation,
        latency_seconds=None if graded is None else graded.latency_seconds,
        original_deadline=None if graded is None else graded.original_deadline,
        result_epoch=None if graded is None else graded.result_epoch,
        diagnostics=(
            decision.diagnostics if graded is None else decision.diagnostics + graded.diagnostics
        ),
    )


def _consumption(*, recovery_store_root: Path, attempt_id: str) -> RecoveryConsumption | None:
    """The attempt's consumption grade, or `None` when no record could be read."""
    loaded = read_recovery_record(
        path=recovery_record_path(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    )
    if loaded.payload is None:
        return None
    return recovery_consumption(payload=loaded.payload)

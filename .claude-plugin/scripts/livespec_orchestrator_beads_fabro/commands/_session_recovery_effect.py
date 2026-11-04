"""The execution receipt: what a sanctioned recovery command durably did.

Split from `_session_recovery_execution` by cohesion: that module decides
WHETHER to run a command, and this one owns the receipt that records what ran —
its value shape, the two seams a caller supplies, and the one write that puts
the effect and its evidence onto the attempt.

`contracts.md` section "Launch obligations and consumed recovery" fixes what a
receipt carries: "An execution receipt carries causal source evidence,
command/action identity, build, attempt identity, start/end observation and
resulting effect/next action." The identities this fleet can supply mechanically
are the command's own identity and the next action it leaves behind, so those
ride on the value; the attempt identity, the start observation and the end
observation are already the record's, and duplicating them here would be a
second place for them to disagree.

WHY THE NEXT ACTION RIDES WITH THE EFFECT. The clause names "resulting
effect/next action" as ONE thing a receipt carries, and that pairing is
load-bearing: a next action recomputed after the fact is a fresh decision taken
against evidence that has since moved, wearing the authority of a receipt.
Carrying it on the effect means the action a reader sees is the action the
command that ran actually left.

WHY A PARTIAL RECORDED EFFECT READS AS NO EFFECT. `recorded_effect` answers
`None` for a present-but-incomplete triple. The alternative is to read what is
there and default the rest, which converts an interrupted write into a COMPLETED
execution — and the convergence rule then returns that half receipt to every
later consumer as the one effect, so nothing ever runs the command. Reading it as
absent routes the attempt into the durable-effect lookup instead, which is the
surface that can decide.

WHY THE EFFECT AND ITS EVIDENCE LAND IN ONE WRITE. They are the same
observation. A record carrying the `executed` transition without the effect
would read to the next pass as an ambiguous START and send it to look up
something already in hand; a record carrying the effect without the transition
would be consumed work that the consumption grade reports as unconsumed.

WHY THE WRITE RE-READS INSIDE THE LOCK AND CAN REPORT A VANISHED RECORD. The
caller graded its standing against a read taken before the lock, so the record
can be gone by the time the write happens. The three outcomes are kept apart —
written, vanished, lock unavailable — because only the first may be reported as
an execution, and a vanished record must not be recreated from this payload: the
transitions a previous consumer wrote would not be in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_EXECUTED,
    read_recovery_record,
    recovery_record_path,
    write_recovery_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_lock import (
    LockBudget,
    run_with_wait_store_lock,
)

__all__: list[str] = [
    "RecoveryEffect",
    "RecoveryEffectReader",
    "SanctionedCommand",
    "record_recovery_effect",
    "recorded_effect",
]


@dataclass(frozen=True, kw_only=True)
class RecoveryEffect:
    """What one sanctioned recovery command durably did, and what it left to do."""

    operation: str
    identity: str
    next_action: str

    def record_payload(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "next_action": self.next_action,
            "operation": self.operation,
        }


class RecoveryEffectReader(Protocol):
    """The durable-effect lookup an ambiguous execution is resolved by.

    Deliberately read-only, and deliberately keyed on the ATTEMPT id rather
    than on anything the half-written record holds: the record is what the
    crash interrupted, so the canonical attempt identity is all a resolving
    pass may trust.
    """

    def observe(self, *, attempt_id: str) -> RecoveryEffect | None: ...


class SanctionedCommand(Protocol):
    """The one effect the execution surface may cause, supplied by its caller.

    A protocol rather than a command string is what keeps "No arbitrary shell
    predicate/result implementation" structural: there is no interpolation and
    no predicate anywhere in this family, so no edit to it can introduce one
    without widening this signature — which is the change a reviewer sees.

    It answers with what it durably did, or `None` when it cannot say, which is
    an AMBIGUOUS outcome rather than a failure: a command that ran and could
    not report is indistinguishable from one that never started.
    """

    def __call__(self, *, attempt_id: str, operation: str) -> RecoveryEffect | None: ...


def recorded_effect(*, payload: dict[str, object]) -> RecoveryEffect | None:
    """The effect a record already names, or `None` while it names none."""
    recorded = payload["effect"]
    if not isinstance(recorded, dict):
        return None
    fields = cast("dict[str, object]", recorded)
    operation = fields.get("operation")
    identity = fields.get("identity")
    next_action = fields.get("next_action")
    readable = (
        isinstance(operation, str) and isinstance(identity, str) and isinstance(next_action, str)
    )
    if not readable:
        return None
    return RecoveryEffect(
        operation=cast("str", operation),
        identity=cast("str", identity),
        next_action=cast("str", next_action),
    )


def record_recovery_effect(
    *,
    recovery_store_root: Path,
    attempt_id: str,
    effect: RecoveryEffect,
    observed_at: float,
    lock_budget: LockBudget | None = None,
) -> bool | None:
    """Write one effect and its evidence transition in a single locked mutation.

    `True` wrote it, `False` found no record to write onto, and `None` could not
    take the store lock within the caller's budget. The three are distinct
    because only `True` may be reported as an execution.
    """
    path = recovery_record_path(recovery_store_root=recovery_store_root, attempt_id=attempt_id)
    return run_with_wait_store_lock(
        wait_store_root=recovery_store_root,
        budget=lock_budget,
        action=lambda: _record_recovery_effect(path=path, effect=effect, observed_at=observed_at),
    )


def _record_recovery_effect(*, path: Path, effect: RecoveryEffect, observed_at: float) -> bool:
    loaded = read_recovery_record(path=path)
    if loaded.payload is None:
        return False
    payload = loaded.payload
    payload["effect"] = effect.record_payload()
    entries = cast("list[object]", payload["transitions"])
    entries.append(
        {
            "detail": effect.record_payload(),
            "observed_at": observed_at,
            "transition": TRANSITION_EXECUTED,
        }
    )
    write_recovery_record(path=path, payload=payload)
    return True

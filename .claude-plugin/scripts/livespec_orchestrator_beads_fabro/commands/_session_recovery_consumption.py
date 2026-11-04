"""Whether one recovery attempt has been CONSUMED, and the latency it actually took.

PURE. `contracts.md` section "Launch obligations and consumed recovery" states
the distinction this module exists to keep: "Receipt or claim alone MUST NOT
mark recovery consumed. Successful recovery execution MUST NOT discharge the
original result unless the relay-owned authoritative reader establishes
fulfillment." Scenario 162 is the same rule read from the other side — a
produced notification, an acknowledged receipt and a claimed lease leave
"recovery unconsumed and the original result outstanding".

WHY THE VOCABULARY HAS NO WORD FOR FULFILLMENT. `CONSUMPTION_STATES` holds
exactly two members, and the omission is the enforcement: a grade that could
report `fulfilled` would be a second satisfaction model, which the same section
forbids outright, and every surface reading this grade would then have a way to
discharge an obligation without consulting the relay's reader. So the grade
reports the required result IDENTITY it leaves outstanding instead, which is
what a caller needs in order to go and ask the authority that owns it.

WHY EXECUTION EVIDENCE IS THE ONE CONSUMING OBSERVATION. The clause separates
execution START from execution EVIDENCE, and only the second is evidence that
anything ran: a `started` transition with no evidence beside it is exactly the
ambiguous crash the execution surface has to resolve by looking the effect up.
Reading `started` as consumption would retire that whole question.

WHY LATENCY IS MEASURED FROM THE NOTIFICATION AND NOT FROM THE CLAIM. The bound
the clause imposes is on the whole path — "Terminal target observation or
original deadline expiry MUST schedule actual authorized diagnosis/recovery
within 60 seconds" — so the interval that matters starts at the TRIGGER a
consumer was notified of. Measuring from the claim would report a prompt
execution for an attempt that sat unclaimed for an hour.

WHY AN UNAVAILABLE LATENCY IS OMITTED AND NAMED. The same section: "Unavailable
values MUST be omitted with an explicit observation diagnostic, never fabricated
as zero." A zero latency is the most convincing possible report of a bound being
met, and it is what a `float` field defaulted from a missing instant would
produce — so the field is optional and its absence carries a diagnostic.

WHY THE INSTANT COMES FROM THE FIRST OBSERVATION OF ITS KIND. A duplicate event
converges on the first observation, so that is the instant a reader may already
have acted on; taking the last would let a late duplicate rewrite a latency that
had already been published.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._session_recovery_records import (
    TRANSITION_EXECUTED,
    TRANSITION_NOTIFICATION,
    observed_transitions,
)

__all__: list[str] = [
    "CONSUMPTION_CONSUMED",
    "CONSUMPTION_STATES",
    "CONSUMPTION_UNCONSUMED",
    "DIAGNOSTIC_LATENCY_UNOBSERVABLE",
    "RecoveryConsumption",
    "recovery_consumption",
    "transition_instant",
]

CONSUMPTION_UNCONSUMED = "unconsumed"
CONSUMPTION_CONSUMED = "consumed"

# Two members, deliberately. See the module docstring: a third meaning
# "fulfilled" would be the second satisfaction model the clause forbids.
CONSUMPTION_STATES: tuple[str, ...] = (CONSUMPTION_UNCONSUMED, CONSUMPTION_CONSUMED)

DIAGNOSTIC_LATENCY_UNOBSERVABLE = "latency-unobservable"


@dataclass(frozen=True, kw_only=True)
class RecoveryConsumption:
    """What one attempt's record observes, and the one result it leaves outstanding.

    The three relay-owned identities are carried AS READ rather than
    recomputed, so a reader can see that a consumed recovery left the original
    deadline and epoch exactly where they were — which is how "a declared
    changed approach does not reset the original result deadline" is checkable
    from the grade alone.
    """

    state: str
    observed: tuple[str, ...]
    duplicate_count: int
    fenced_count: int
    latency_seconds: float | None
    diagnostics: tuple[str, ...]
    required_result_identity: str
    result_epoch: int
    original_deadline: str

    @property
    def consumed(self) -> bool:
        return self.state == CONSUMPTION_CONSUMED


def transition_instant(*, payload: dict[str, object], transition: str) -> float | None:
    """When one transition was FIRST observed, or `None` when that is unreadable.

    `None` covers both an absent transition and an entry whose instant is not a
    number, because the consequence is the same for every caller: there is no
    instant to measure from, and inventing one would publish a latency nobody
    observed.
    """
    entries = cast("list[object]", payload["transitions"])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fields = cast("dict[str, object]", entry)
        if fields.get("transition") != transition:
            continue
        instant = fields.get("observed_at")
        if isinstance(instant, int | float) and not isinstance(instant, bool):
            return float(instant)
        return None
    return None


def recovery_consumption(*, payload: dict[str, object]) -> RecoveryConsumption:
    """Grade one attempt's record: consumed only on recorded execution evidence."""
    observed = observed_transitions(payload=payload)
    consumed = TRANSITION_EXECUTED in observed
    latency = _latency_seconds(payload=payload) if consumed else None
    return RecoveryConsumption(
        state=CONSUMPTION_CONSUMED if consumed else CONSUMPTION_UNCONSUMED,
        observed=observed,
        duplicate_count=cast("int", payload["duplicate_count"]),
        fenced_count=cast("int", payload["fenced_count"]),
        latency_seconds=latency,
        diagnostics=() if latency is not None else (DIAGNOSTIC_LATENCY_UNOBSERVABLE,),
        required_result_identity=cast("str", payload["required_result_identity"]),
        result_epoch=cast("int", payload["result_epoch"]),
        original_deadline=cast("str", payload["original_deadline"]),
    )


def _latency_seconds(*, payload: dict[str, object]) -> float | None:
    """How long the notified trigger took to produce execution evidence."""
    triggered = transition_instant(payload=payload, transition=TRANSITION_NOTIFICATION)
    executed = transition_instant(payload=payload, transition=TRANSITION_EXECUTED)
    if triggered is None or executed is None:
        return None
    return executed - triggered

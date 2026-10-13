"""WHEN an item whose admission-required chain is empty is looked at again.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "If any potentially reachable node has no eligible candidate, the
item MUST remain ready without a claim or blocked reason, and the Dispatcher
MUST schedule another admission evaluation. ... The scheduled evaluation falls
at the earliest expiry among the holds that empty a chain, and otherwise after
`dispatcher.credential_reprobe_interval_seconds`; no human valve is the remedy
for that wait."

THE WAIT IS A VALUE AND NOTHING HERE SCHEDULES A TIMER. There is no sleep, no
retry, no clock read and no callback: the instant is DERIVED from the verdict
the pass already computed, journaled on the refusal, and reevaluated by the
ordinary unattended loop on its next pass. That is what makes "an expired
timestamp MUST NOT schedule an immediate retry repeatedly" structural rather
than a rule somebody has to honour -- there is no retry mechanism to misuse,
and a pass that meets an elapsed instant simply evaluates once and reschedules
forward.

THE EARLIEST EXPIRY IS TAKEN ACROSS EVERY EMPTIED CHAIN, not from the first
exhausted node. The two are easy to confuse and the wrong one is invisible: it
produces a well-formed instant in the right format that merely leaves the item
waiting past the moment it became dispatchable again. The clause says "the
holds that empty a chain" -- plural, unscoped to a node -- because the item is
blocked by all of them jointly and becomes evaluable again when the FIRST of
them retires.

A LEGACY PROVIDER RECORD IS ONE OF THOSE HOLDS. Reading typed expiries alone
would route every legacy-governed wait onto the reprobe dial, which is the
"otherwise" arm reached while a hold does in fact govern -- a wait reported as
"no hold governs this" over a record that is governing it. `SkippedCandidate`
therefore carries the expiry of whichever durable record removed the
candidate, typed or legacy, and this reads both through one field.

THE TWO CONDITIONS ARE THE TWO THIS BUILD CAN MEASURE, and the set is
deliberately not wider. Scenario 60 also names an "outstanding confirmation"
and an "unavailable evidence source" as conditions a refusal may report. The
post-expiry availability confirmation turn is not built yet, and an
unobservable hold record does not skip a candidate -- it rides the verdict
uninterpreted -- so neither can empty a chain here. Inventing an arm for
either would put a condition in the record that nothing measured, which is the
same defect in the opposite direction from omitting one. The unobservable set
still rides the refusal record alongside, as a count, because a reader needs to
know an uninterpreted record exists even when it governs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    PROBE_SKIP,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import parse_hold_instant
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "LIVE_HOLD_CONDITION",
    "AvailabilityWait",
    "schedule_availability_wait",
]

# The governing condition a wait reports when a live hold -- typed or legacy --
# is what emptied the chain. A stable machine token rather than prose, so the
# journal is greppable and the attention surface and the refusal cannot word
# the same condition two ways.
LIVE_HOLD_CONDITION = "live-availability-hold"

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True, kw_only=True)
class AvailabilityWait:
    """One scheduled admission reevaluation, and why it is owed.

    `nodes` is EVERY admission-required node left with no eligible candidate,
    not just one. The clause's refusal "names the admission-required node
    lacking an eligible candidate" and a one-element list names it exactly;
    carrying all of them is strictly more informative and cannot misreport a
    single node, whereas picking one would hide the rest of what an operator
    has to clear before the item moves.

    `hold_expiries` is the expiry of every hold that emptied a chain, earliest
    first and de-duplicated. It is EMPTY on the reprobe arm rather than
    carrying a borrowed instant, because "no hold governs the refusal" is a
    fact the record has to be able to state "without inventing a hold identity
    or expiry".
    """

    nodes: tuple[str, ...]
    governing_condition: str
    scheduled_at: str
    hold_expiries: tuple[str, ...] = ()


def schedule_availability_wait(
    *,
    verdict: AcpPreflightVerdict,
    now_iso: str,
    reprobe_interval_seconds: int,
) -> AvailabilityWait | None:
    """The reevaluation this verdict owes, or `None` when nothing is waiting.

    `None` is returned for a verdict with no exhausted chain -- including every
    verdict a repository with no fallback configuration can produce, and every
    graph-shape or configuration refusal, which names no node and is not a
    wait but a fault whose remedy is a committed change.
    """
    if not verdict.exhausted:
        return None
    expiries = _emptying_hold_expiries(verdict=verdict)
    if expiries:
        return AvailabilityWait(
            nodes=verdict.exhausted,
            governing_condition=LIVE_HOLD_CONDITION,
            scheduled_at=expiries[0],
            hold_expiries=expiries,
        )
    return AvailabilityWait(
        nodes=verdict.exhausted,
        governing_condition=PROBE_SKIP,
        scheduled_at=_advanced(now_iso=now_iso, seconds=reprobe_interval_seconds),
    )


def _emptying_hold_expiries(*, verdict: AcpPreflightVerdict) -> tuple[str, ...]:
    """Every durable-record expiry behind an emptied chain, earliest first."""
    expiries = {
        skip.expires_at for skip in _emptying_skips(verdict=verdict) if skip.expires_at is not None
    }
    return tuple(sorted(expiries))


def _emptying_skips(*, verdict: AcpPreflightVerdict) -> tuple[SkippedCandidate, ...]:
    """The skips that emptied the exhausted chains, and only those.

    Scoped to the EXHAUSTED nodes on purpose. A node whose chain still holds a
    candidate may also carry skips -- that is the ordinary fallback path -- and
    those records are not holding anything back, so letting their expiries
    schedule the wait would make a healthy fallback decide when a blocked item
    is looked at again.
    """
    exhausted = frozenset(verdict.exhausted)
    return tuple(
        skip
        for preflight in verdict.nodes
        if preflight.node in exhausted
        for skip in preflight.skipped
    )


def _advanced(*, now_iso: str, seconds: int) -> str:
    """`now` advanced by the configured interval, as a journal instant.

    The clock is the Dispatcher's own `utc_now_iso()`, so a value this cannot
    parse is a bug rather than an expected error, and it raises instead of
    answering: both soft alternatives are worse. Falling back to `now` would
    schedule an immediate retry -- the busy loop the clause forbids -- and
    omitting the instant would leave the refusal record without the one field
    an operator reads to learn when the item moves again.
    """
    now = parse_hold_instant(text=now_iso)
    if now is None:
        msg = f"evaluation instant {now_iso!r} is not an ISO-8601 instant"
        raise ValueError(msg)
    return (now + timedelta(seconds=seconds)).strftime(_ISO_FORMAT)

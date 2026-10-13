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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    PROBE_SKIP,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import parse_hold_instant
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "LIVE_HOLD_CONDITION",
    "SCHEDULED_AT_KEY",
    "SUPERSEDED_AT_KEY",
    "AvailabilityWait",
    "recorded_availability_wait",
    "schedule_availability_wait",
]

# The governing condition a wait reports when a live hold -- typed or legacy --
# is what emptied the chain. A stable machine token rather than prose, so the
# journal is greppable and the attention surface and the refusal cannot word
# the same condition two ways.
LIVE_HOLD_CONDITION = "live-availability-hold"

# The record key the scheduled instant is journaled under. Named here, beside
# the value, so the refusal that writes it and anything that later reads a
# recorded schedule back agree on one spelling rather than on two literals.
SCHEDULED_AT_KEY = "scheduled_reevaluation_at"

# The record key the PRIOR pass's instant is journaled under, so a reader can
# see which schedule this pass reevaluated instead of inferring it from two
# rows' timestamps.
SUPERSEDED_AT_KEY = "superseded_scheduled_reevaluation_at"

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

    `superseded_at` and `reevaluation_was_due` describe the schedule a PRIOR
    pass recorded, as reconstructed from the journal. They are what makes
    "reevaluated once per loop pass" legible rather than inferred: a pass that
    met an elapsed instant says so and names it, and the fresh `scheduled_at`
    beside it is the forward reschedule. A retry against a dead deadline would
    report the elapsed instant as its own schedule, and a busy loop would
    append several rows within one pass; neither can produce this shape.
    """

    nodes: tuple[str, ...]
    governing_condition: str
    scheduled_at: str
    hold_expiries: tuple[str, ...] = ()
    superseded_at: str | None = None
    reevaluation_was_due: bool = False

    def elapsed(self, *, now_iso: str) -> bool:
        """Whether this scheduled instant has already passed.

        An unreadable instant on either side reports NOT elapsed, which leaves
        the schedule standing. The opposite default would make one malformed
        record read as a wait that is due on every pass forever, and "due" is
        the direction that spends work.
        """
        scheduled = parse_hold_instant(text=self.scheduled_at)
        now = parse_hold_instant(text=now_iso)
        if scheduled is None or now is None:
            return False
        return scheduled <= now

    @property
    def record(self) -> dict[str, object]:
        """The journal fields a containment refusal reports this wait as.

        Rendered HERE rather than at the refusal so the one surface that owns
        the wait owns its spelling too: the refusal, an attention row and any
        later reader of a recorded schedule would otherwise each name these
        fields themselves, and three spellings of one fact is how two of them
        come to disagree about which key carries the instant.
        """
        return {
            "governing_condition": self.governing_condition,
            "nodes": list(self.nodes),
            SCHEDULED_AT_KEY: self.scheduled_at,
            "hold_expiries": list(self.hold_expiries),
            SUPERSEDED_AT_KEY: self.superseded_at,
            "reevaluation_was_due": self.reevaluation_was_due,
        }


def schedule_availability_wait(
    *,
    verdict: AcpPreflightVerdict,
    now_iso: str,
    reprobe_interval_seconds: int,
    recorded: AvailabilityWait | None = None,
) -> AvailabilityWait | None:
    """The reevaluation this verdict owes, or `None` when nothing is waiting.

    `None` is returned for a verdict with no exhausted chain -- including every
    verdict a repository with no fallback configuration can produce, and every
    graph-shape or configuration refusal, which names no node and is not a
    wait but a fault whose remedy is a committed change.

    `recorded` is the schedule a PRIOR pass journaled, as reconstructed from
    the journal, and it is carried onto the result so the refusal can say
    which instant this evaluation superseded and whether it had lapsed. Its
    `None` default means exactly "no prior schedule was recorded", which is
    the honest answer for a first pass and for a journal that records none.
    """
    if not verdict.exhausted:
        return None
    return _superseding(
        wait=_scheduled(
            verdict=verdict, now_iso=now_iso, reprobe_interval_seconds=reprobe_interval_seconds
        ),
        recorded=recorded,
        now_iso=now_iso,
    )


def _scheduled(
    *,
    verdict: AcpPreflightVerdict,
    now_iso: str,
    reprobe_interval_seconds: int,
) -> AvailabilityWait:
    """The instant and condition this evaluation owes, before supersession."""
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


def _superseding(
    *,
    wait: AvailabilityWait,
    recorded: AvailabilityWait | None,
    now_iso: str,
) -> AvailabilityWait:
    """`wait`, carrying the recorded schedule this evaluation supersedes.

    A first pass supersedes nothing and the two fields stay at their
    unanswered defaults, which `record` still writes as a null and a false
    rather than omitting: an omitted key is indistinguishable from a record
    written by a build predating these fields, so a reader could not tell "no
    prior schedule existed" from "this pass never asked".
    """
    if recorded is None:
        return wait
    return replace(
        wait,
        superseded_at=recorded.scheduled_at,
        reevaluation_was_due=recorded.elapsed(now_iso=now_iso),
    )


def recorded_availability_wait(*, records: Iterable[Mapping[str, Any]]) -> AvailabilityWait | None:
    """The NEWEST schedule a prior pass journaled, or `None` when none did.

    This is how a scheduled wait survives a Dispatcher restart: the schedule
    is reconstructed from the append-only journal rather than from process
    state, so a restarted Dispatcher reads the same instant the pass before it
    recorded. The walk is newest-last, so a later pass's schedule supersedes
    an earlier one for the same reason the hold ledger's clearance walk does
    -- the journal's order IS the chronology.

    WHAT IT DOES NOT DO IS GATE A PASS, and that is a correctness requirement
    rather than a simplification. Admission is decided from LIVE evidence on
    every pass, so an operator clearance "MUST make the affected wait eligible
    for immediate reevaluation"; a reconstruction that suppressed evaluation
    until its recorded instant would hold the item past that clearance and
    would also outlive the hold that justified it.

    A record missing or mistyping ANY field a schedule carries is SKIPPED
    rather than partially read. Every other dispatcher stage writes to this
    same journal, so a half-matching record is some other stage's line, and
    reading one would invent a schedule out of a field that means something
    else.
    """
    latest: AvailabilityWait | None = None
    for record in records:
        parsed = _parse_recorded_wait(record=record)
        if parsed is not None:
            latest = parsed
    return latest


def _parse_recorded_wait(*, record: Mapping[str, Any]) -> AvailabilityWait | None:
    """One journaled schedule, or `None` when this record is not one."""
    scheduled_at = record.get(SCHEDULED_AT_KEY)
    condition = record.get("governing_condition")
    nodes = record.get("nodes")
    expiries = record.get("hold_expiries")
    if (
        not isinstance(scheduled_at, str)
        or not isinstance(condition, str)
        or not isinstance(nodes, list)
        or not isinstance(expiries, list)
    ):
        return None
    return AvailabilityWait(
        nodes=tuple(str(node) for node in cast("list[object]", nodes)),
        governing_condition=condition,
        scheduled_at=scheduled_at,
        hold_expiries=tuple(str(expiry) for expiry in cast("list[object]", expiries)),
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

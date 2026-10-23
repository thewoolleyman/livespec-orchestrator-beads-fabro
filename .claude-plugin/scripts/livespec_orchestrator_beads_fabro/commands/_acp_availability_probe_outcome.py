"""WHAT one confirmation turn's ending MEANS, and which one confirms.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Availability is
confirmed only by a successfully completed ACP prompt turn using the
candidate's pinned adapter version, requested model and effort, and projected
worker credential identity. Session creation, process exit alone, timeout,
cancellation, and an ACP refusal do not confirm availability. ... An eligible
refusal creates a new occurrence-time-scoped hold. Any other probe failure
skips that candidate for the current evaluation, creates no hold, and allows
selection to continue to later eligible candidates."

PURE, AND THE GRADING ONLY. It mints no hold, writes no journal, reads no
configuration and reaches no factory: `_acp_availability_probe` beside it owns
the probe's SHAPE, `_acp_availability_probe_records` owns the two records an
ending produces, and `_acp_availability_probe_run` performs the turn and fills
the observation this grades. One concern each, and the direction of every edge
between them is what keeps the four acyclic.

THE FIVE UNCONFIRMED ENDINGS ARE KEPT APART RATHER THAN COLLAPSED, which is the
one decision an editor is most likely to undo on the grounds that the clause
treats them alike. It does not: downstream they take THREE routes. An eligible
REFUSAL mints a hold whose expiry runs from the probe's own occurrence time; a
TIMEOUT must mint nothing, because a turn the Dispatcher terminated measured no
provider; and a process exit, a bare session and a cancellation are neither.
Returning one boolean would make a terminated probe indistinguishable from a
measured outage, and the hold it then minted would skip the candidate for
fifteen minutes on evidence nobody gathered.

THE PRECEDENCE IS NOT ARBITRARY, and three of its five steps are load-bearing.

The BOUND is read FIRST, before the recorded text. A turn this Dispatcher killed
has whatever ending the kill produced, and the engine's own record of a
terminated ACP turn can perfectly well carry the provider's last sentence -- so
a grader reading the text first would mint a hold from a measurement it
interrupted. The clause is explicit that a timed-out probe creates no hold, and
putting the bound first is how that becomes unreachable rather than merely
unwritten.

The COMPLETED TURN is read SECOND, ahead of every failure arm. A probe run is
one node, but a run-level failure block legitimately carries a sentence about
something other than the turn -- the engine records a run's terminal cause, and
a successful turn inside a run that then failed elsewhere is still a completed
turn. Reading the failure first would discard the one ending that confirms, on
evidence that is not about it. (The DELIBERATE companion to this is in
"A provider refusal booked as a successful turn is a failed attempt": a turn
recorded as succeeded whose OUTPUT matches a `turn.final_output` signature is a
failed attempt, and the clause says in as many words that it "MUST NOT count
... as a successfully completed availability confirmation turn". That is graded
where the output is read, by the classifier the refusal arm consults, and not
here: this module sees no turn output, which is what keeps the contract's
"never an arbitrary exec-output tail" rule structural.)

The SESSION and the PROCESS EXIT are told apart by one fact and no inference:
whether the attempt carries the `agent.acp.started` event. The adapter-launch
clause already fixes that reading -- "The prompt boundary is conservatively
considered crossed when that attempt has an `agent.acp.started` event; this
event precedes prompt submission" -- so a started attempt that completed no
turn is exactly the clause's "session creation", and an attempt without it is
exactly "process exit alone". Neither is derived from a message.

THE VOCABULARY IS CLOSED, and `PROBE_ENDINGS` is the enumeration rather than a
comment, so a consumer can exhaust it. Exactly one member confirms, which is
asserted by its own test rather than left to the reader of this docstring.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

__all__: list[str] = [
    "PROBE_CANCELLED",
    "PROBE_ENDINGS",
    "PROBE_PROCESS_EXIT",
    "PROBE_REFUSED",
    "PROBE_SESSION_CREATED",
    "PROBE_TIMED_OUT",
    "PROBE_TURN_COMPLETED",
    "PROBE_UNCONFIRMED_ENDINGS",
    "AcpProbeObservation",
    "probe_confirms",
    "probe_ending",
]

# The ONE ending that confirms availability.
PROBE_TURN_COMPLETED = "turn-completed"

# The five that do not, each spelled for the clause's own word for it so a
# journal row reads back as the sentence it was graded against.
PROBE_SESSION_CREATED = "session-created"
PROBE_PROCESS_EXIT = "process-exit"
PROBE_TIMED_OUT = "timed-out"
PROBE_CANCELLED = "cancelled"
PROBE_REFUSED = "acp-refusal"

# The closed vocabulary, confirming member first. Ordered so a reader of the
# tuple meets the one ending that confirms before the five that do not.
PROBE_ENDINGS: tuple[str, ...] = (
    PROBE_TURN_COMPLETED,
    PROBE_SESSION_CREATED,
    PROBE_PROCESS_EXIT,
    PROBE_TIMED_OUT,
    PROBE_CANCELLED,
    PROBE_REFUSED,
)

# Derived rather than restated, so the two can never disagree about whether an
# ending confirms -- the failure mode being a member listed in both.
PROBE_UNCONFIRMED_ENDINGS: tuple[str, ...] = tuple(
    ending for ending in PROBE_ENDINGS if ending != PROBE_TURN_COMPLETED
)


@dataclass(frozen=True, kw_only=True)
class AcpProbeObservation:
    """One launched confirmation turn's ending, as the launcher read it.

    FIVE FIELDS AND NOTHING ELSE, which is the contract's "never an arbitrary
    exec-output tail, prompt, tool/test/review output, or run log" made
    structural: a caller holding a run log has nowhere to put it.

    `turn_completed` is the probe node attempt recorded SUCCEEDED by the
    factory, which is the only thing that confirms. `acp_started` is whether
    that attempt carries the `agent.acp.started` event -- the one fact that
    tells a created session from an adapter that exited before the protocol.
    `timed_out` is the probe's own bound having fired, client-side or
    node-side. `failure` is the run's recorded failure block, read for its
    provider sentence by the refusal arm and by nothing else here.
    """

    turn_completed: bool
    acp_started: bool
    cancelled: bool
    timed_out: bool
    failure: FabroFailureDetail | None


def probe_confirms(*, ending: str) -> bool:
    """Whether this ending confirms availability.

    An equality test against the ONE confirming member rather than a membership
    test against the five that are not, because an ending this module does not
    know is not a confirmation: a token from a build this one has never seen
    must fail closed, and a negated membership test would admit it.
    """
    return ending == PROBE_TURN_COMPLETED


def probe_ending(*, observation: AcpProbeObservation) -> str:
    """Which of the six endings this observation is.

    Total over the six, in the precedence the module docstring argues for. The
    final arm is the PROCESS EXIT rather than a fallback: an attempt that
    neither completed a turn, nor was terminated or cancelled, nor opened a
    session, is the adapter having exited before the protocol completed.
    """
    if observation.timed_out:
        return PROBE_TIMED_OUT
    if observation.turn_completed:
        return PROBE_TURN_COMPLETED
    if observation.cancelled:
        return PROBE_CANCELLED
    if _refused(observation=observation):
        return PROBE_REFUSED
    if observation.acp_started:
        return PROBE_SESSION_CREATED
    return PROBE_PROCESS_EXIT


def _refused(*, observation: AcpProbeObservation) -> bool:
    """Whether the attempt was refused OVER the protocol rather than before it.

    BOTH halves are required and neither alone is this ending. A recorded
    sentence with no session behind it is a pre-turn fault -- the contract's "A
    mere pre-turn failure is not provider evidence" -- and a started session
    with nothing recorded is the bare-session ending above. Together they are an
    attempt that reached the protocol and came back refused, which is the one
    unconfirmed ending whose cause the classifier may then grade for a hold.
    """
    failure = observation.failure
    if not observation.acp_started or failure is None:
        return False
    return failure.cause is not None and failure.cause.strip() != ""

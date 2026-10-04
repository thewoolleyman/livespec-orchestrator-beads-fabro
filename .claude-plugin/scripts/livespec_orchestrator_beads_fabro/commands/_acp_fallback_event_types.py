"""The ACP fallback event VOCABULARY: its type names and its record shapes.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority", "Events and projection are compatible, idempotent, and
leak-free": each reactive or actually executed preflight transition emits
a versioned `agent.acp.failover` carrying "stable event id, occurrence
time, node visit, engine attempt, candidate indexes and durations,
from/to display and machine identities, selected hold key, typed
cause/scope, primary-generation fingerprint, and separate full-chain
digest", and exhaustion is "a typed, non-retryable node outcome
preserving the final cause".

THE VOCABULARY IS CLOSED AND ITS EXCLUSIONS ARE NAMED. A run's stream
carries `agent.acp.started`, the native `agent.failover`, and the
engine-internal `agent.acp.side_effect` alongside the two projectable
types. The contract is explicit that the side-effect ledger "is
engine-internal evidence and is not a hold source" and that "Existing
`agent.failover` events and stored-run consumers remain unchanged", so
both are named here as constants rather than left as absences a reader
would have to infer.

THE FAILING IDENTITY IS THE `from` CANDIDATE. A transition names two
candidates and only one of them failed; keying the hold on `to` would
hold the candidate that RESCUED the node and leave the broken one
eligible, which is the precise inversion the fallback order exists to
prevent. Exhaustion carries only `from`, the final candidate whose cause
is preserved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
)

__all__: list[str] = [
    "ACP_EVENT_SCHEMA_VERSION",
    "ACP_EXHAUSTED_EVENT",
    "ACP_FAILOVER_EVENT",
    "ACP_PROJECTED_EVENT_TYPES",
    "ACP_SIDE_EFFECT_EVENT",
    "ACP_STARTED_EVENT",
    "AcpEventScan",
    "AcpFallbackEvent",
    "AcpNodeStart",
    "event_failure",
]

ACP_FAILOVER_EVENT = "agent.acp.failover"
ACP_EXHAUSTED_EVENT = "agent.acp.exhausted"

# Read but never projected into a hold: a started attempt is evidence about
# WHICH candidate ran, which is what the model-fallback warning's clearance
# rule needs ("a primary node attempt ... began after the warning"). It is
# not evidence of a failure and mints nothing.
ACP_STARTED_EVENT = "agent.acp.started"

# Named so the exclusion is legible rather than implicit in the tuple below:
# the side-effect ledger proves onset to the ENGINE and says nothing about
# provider availability.
ACP_SIDE_EFFECT_EVENT = "agent.acp.side_effect"

ACP_PROJECTED_EVENT_TYPES: tuple[str, ...] = (ACP_FAILOVER_EVENT, ACP_EXHAUSTED_EVENT)

ACP_EVENT_SCHEMA_VERSION = 1


@dataclass(frozen=True, kw_only=True)
class AcpFallbackEvent:
    """One schema-v1 transition or exhaustion, read onto this repo's vocabulary."""

    event_id: str
    event_type: str
    occurred_at: str
    node: str
    node_visit: int
    engine_attempt: int
    from_candidate_index: int
    from_display_name: str
    from_candidate_key: str
    from_availability_key: str
    to_candidate_index: int | None
    to_display_name: str | None
    to_candidate_key: str | None
    hold_key: str
    cause: str
    scope: str
    primary_generation: str
    full_chain: str
    attempted: tuple[str, ...]
    skipped: tuple[str, ...]
    attempted_durations_ms: tuple[int, ...] = ()

    @property
    def executed_non_primary(self) -> bool:
        """Whether this transition actually EXECUTED a non-primary candidate.

        "Every ACTUALLY EXECUTED non-primary candidate appends one
        idempotent journal record", and Scenario 127's control is that "an
        unexecuted preflight selection for a node never reached emits no
        fallback warning". Exhaustion executed nothing new -- it is the
        chain running out -- so it carries no `to` index and answers False.
        """
        return self.to_candidate_index is not None and self.to_candidate_index > 0


@dataclass(frozen=True, kw_only=True)
class AcpNodeStart:
    """One `agent.acp.started`: which candidate began a node visit, and when.

    `confirmed_model` and `confirmed_effort` are the values the handler
    established in the agent's own `configOptions` before the first prompt, which
    section "In-protocol model and effort selection" requires the event to carry
    "as additive non-secret fields so a reader can verify which model actually ran
    without reading the command".

    THEY ARE OPTIONAL, AND NOT MERELY TOLERATED. A candidate whose agent takes
    its model in the environment or on the command line requests no session
    options at all and confirms none, so `None` here is the ORDINARY answer for
    most of this fleet rather than a degraded one. That is why their absence
    costs the start nothing: `candidate_index` decides whether a start can be
    read, and a start discarded for want of a confirmation would silently strand
    the model-fallback warning whose clearance rule depends on it.

    `chain_deadline_epoch_ms` is the chain's own ceiling as the engine reported
    it. It is carried as REPORTED CONTEXT and deliberately not used to close an
    attempt's window: the deadline bounds when a NEW candidate may start, not
    when the one that succeeded must finish, so closing the winner's window
    there would silently drop every token it spent afterwards. `None` is an
    engine that did not report one -- never a substituted instant, which in
    epoch-millisecond terms would be a real moment in 1970.
    """

    node: str
    node_visit: int
    candidate_index: int
    occurred_at: str
    primary_generation: str
    chain_deadline_epoch_ms: int | None = None
    confirmed_model: str | None = None
    confirmed_effort: str | None = None

    @property
    def primary(self) -> bool:
        """Whether this attempt was candidate ZERO -- the node's own primary."""
        return self.candidate_index == 0


@dataclass(frozen=True, kw_only=True)
class AcpEventScan:
    """Every projectable event in one run's stream, plus what could not be read."""

    events: tuple[AcpFallbackEvent, ...]
    unobservable: tuple[Mapping[str, object], ...]
    starts: tuple[AcpNodeStart, ...] = ()


def event_failure(*, event: AcpFallbackEvent) -> AcpAvailabilityFailure:
    """The typed availability failure one event's FROM candidate suffered.

    Built here rather than in the ledger writer because the scope decides
    the key shape: a domain record must carry no `candidate_key` and a
    candidate record must carry one, and `parse_hold_record` refuses
    either mistake. The event already states its scope, so the shaping is
    a read rather than a judgement.
    """
    domain = event.scope == DOMAIN_SCOPE
    return AcpAvailabilityFailure(
        cause=event.cause,
        scope=event.scope,
        hold_key=event.hold_key,
        availability_key=event.from_availability_key,
        candidate_key=None if domain else event.from_candidate_key,
        source=event.event_type,
    )

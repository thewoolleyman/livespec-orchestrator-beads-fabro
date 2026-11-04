"""ONE availability attempt derived from a factory run, and what it stands for.

The leaf of the host-wide availability read: the attempt's identity, its
bounded expiry, the typed hold it stands for, and the journal line that audits
it. `_acp_factory_hold_evidence` next door owns the READ that produces these
attempts; the direction of the one edge between them is what keeps the pair
acyclic, and it mirrors `_acp_hold_records` / `_acp_hold_ledger` one level
down -- the record knows nothing about any reader.

That split is also what makes every decision here exercisable with no factory
at all: nothing in this module performs IO, reads configuration, or takes a
clock. Expiry in particular is computed from the attempt's own occurrence
instant and from no other input, which is `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" → "Expiry is computed from
occurrence time and never from ingestion" expressed as an absent parameter
rather than as a rule somebody has to remember.

THE ELIGIBLE CAUSE IS DOMAIN-SCOPED, and that is the same choice the built-in
quota signatures make: the spent allowance belongs to the account, so holding
one candidate would leave every sibling on the same provider dispatching into
the same refusal. Scenario 127's "A provider-limit failure releases the item
and re-dispatches it to the next eligible candidate" grades it.

THE JOURNAL IS AN AUDIT REFERENCE AND NEVER THE AUTHORITY. "Dispatch journals
MAY record audit references but MUST NOT be the sole authority for holds", so
`factory_hold_observation_record` writes the ordinary v1 observation PLUS the
factory run it was derived from. A reader of the journal is pointed back at the
record that can re-derive it rather than left holding the only copy.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_EVIDENCE_KINDS,
    HOLD_INTERVAL,
    HOLD_SCHEMA_VERSION,
    AcpAvailabilityHold,
    hold_observation_record,
    observation_id,
    parse_hold_instant,
)

__all__: list[str] = [
    "AUDIT_REFERENCE_KEY",
    "FACTORY_EVIDENCE_KIND",
    "FACTORY_EVIDENCE_SOURCE",
    "PROVIDER_LIMIT_CAUSE",
    "FactoryHoldObservation",
    "attempt_expiry",
    "factory_hold_observation_record",
    "observation_hold",
]

# The journal key a derived record's AUDIT reference lands under. The journal
# is never the authority for these holds, so the line names the factory run
# the record can be re-derived from rather than standing on its own.
AUDIT_REFERENCE_KEY = "audit_reference"

# The evidence kind a TERMINAL-failure-derived hold is minted under. Read off
# the hold writer's own closed set rather than spelled again, so a rename there
# cannot leave this call site silently naming a kind that writer refuses. The
# first member of that set is the retired failover event's kind, which v127
# left in the closed set because existing records still carry it: the index
# here is therefore load-bearing and NOT a stand-in for "the only kind".
FACTORY_EVIDENCE_KIND = HOLD_EVIDENCE_KINDS[1]

# The diagnostic channel this verdict was read off: the engine's own recorded
# cause chain for the failing node attempt.
FACTORY_EVIDENCE_SOURCE = "process.terminal_diagnostic"

# The ratified cause a spent provider allowance carries, identical to the one
# the built-in provider-limit signatures declare.
PROVIDER_LIMIT_CAUSE = "quota"

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True, kw_only=True)
class FactoryHoldObservation:
    """One availability attempt, as the factory's own records identify it.

    The six identifying fields are the clause's own list: the resolved
    `factory`, the `repository` whose dispatch ran, the `run_id`, the
    `node_attempt`, the candidate entitlement as the
    `(availability_key, candidate_key)` pair, and the `occurred_at` instant.
    `repository` is OPTIONAL because an `omitempty`-sparse row carries no
    repository label, and a derived name would report a dispatch nobody made.
    """

    factory: str
    repository: str | None
    run_id: str
    node_attempt: str
    availability_key: str
    candidate_key: str | None
    cause: str
    occurred_at: str

    @property
    def run_reference(self) -> str:
        """The factory run reference this observation is re-derivable from.

        It is also what makes the derived observation id STABLE: the id
        digests its evidence, and this reference is a fact of the FACTORY's
        record rather than of the reading, so two Dispatchers deriving one
        attempt mint one id instead of two records of the same outage.
        """
        return f"{self.factory}:{self.run_id}:{self.node_attempt}"

    @property
    def expires_at(self) -> str:
        """The bounded expiry this attempt's OCCURRENCE time implies.

        Derived from `occurred_at` alone, with no clock anywhere in reach --
        the same property `hold_observation_record` holds by taking no clock
        parameter, and it matters more here: this evidence is re-read from the
        factory on EVERY admission evaluation, so an expiry computed from the
        reading would make one four-minute outage stand for as long as anyone
        kept looking at it.
        """
        return attempt_expiry(occurred_at=self.occurred_at)


def attempt_expiry(*, occurred_at: str) -> str:
    """One attempt's bounded expiry, or the occurrence itself when unreadable.

    The bound is the SAME `HOLD_INTERVAL` a journal-projected observation
    takes, read off the hold writer rather than respelled: the two valves
    observe the same kind of outage on the same factory, and a derived hold
    that outlived its projected counterpart would be a behaviour change
    nobody ratified.

    An occurrence nobody can read is not an instant fifteen minutes can be
    added to, so it is carried through UNCHANGED rather than replaced: both of
    the record's instants then say the same unreadable thing, where a computed
    substitute would date the record from the READING. Do NOT mistake that arm
    for a safety net -- `hold_expired` cannot read such a record either and
    reports it as standing. What keeps it harmless is that no derivation here
    can build one: `factory_hold_evidence` formats every `occurred_at` from an
    instant it has already parsed.
    """
    occurred = parse_hold_instant(text=occurred_at)
    if occurred is None:
        return occurred_at
    return (occurred + HOLD_INTERVAL).strftime(_ISO_FORMAT)


def observation_hold(*, observation: FactoryHoldObservation) -> AcpAvailabilityHold:
    """The live schema-v1 hold one derived observation stands for."""
    failure = _observation_failure(observation=observation)
    return AcpAvailabilityHold(
        schema_version=HOLD_SCHEMA_VERSION,
        observation_id=observation_id(
            evidence_kind=FACTORY_EVIDENCE_KIND,
            evidence_id=observation.run_reference,
            failure=failure,
        ),
        scope=failure.scope,
        hold_key=failure.hold_key,
        candidate_key=failure.candidate_key,
        cause=failure.cause,
        occurred_at=observation.occurred_at,
        expires_at=observation.expires_at,
    )


def factory_hold_observation_record(
    *, observation: FactoryHoldObservation, work_item_id: str
) -> dict[str, object] | str:
    """The appendable AUDIT line one derived observation writes, or a refusal.

    "Dispatch journals MAY record audit references but MUST NOT be the sole
    authority for holds." The line is therefore the ORDINARY v1 observation --
    it reads back through `parse_hold_record` to the very hold the evidence
    stands for -- plus the factory run it was derived from, so a reader of the
    journal is pointed at the authority rather than left holding the only
    copy.

    The writer's own refusal is RETURNED rather than swallowed into a record.
    A line whose occurrence nobody can read is an audit reference to nothing:
    the hold it claims to mirror cannot be re-derived from it, which is the
    one property this copy exists to preserve.
    """
    record = hold_observation_record(
        failure=_observation_failure(observation=observation),
        evidence_kind=FACTORY_EVIDENCE_KIND,
        evidence_id=observation.run_reference,
        occurred_at=observation.occurred_at,
        work_item_id=work_item_id,
        node=observation.node_attempt,
    )
    if isinstance(record, str):
        return record
    return {**record, AUDIT_REFERENCE_KEY: observation.run_reference}


def _observation_failure(*, observation: FactoryHoldObservation) -> AcpAvailabilityFailure:
    """The typed verdict this observation carries, scoped to its provider domain.

    `candidate_key` is deliberately absent from the FAILURE even though the
    observation records one: a domain-scoped record must name none -- the hold
    parser refuses one that does -- and the entitlement that ran is identifying
    evidence about the attempt rather than the thing being held.
    """
    return AcpAvailabilityFailure(
        cause=observation.cause,
        scope=DOMAIN_SCOPE,
        hold_key=observation.availability_key,
        availability_key=observation.availability_key,
        candidate_key=None,
        source=FACTORY_EVIDENCE_SOURCE,
    )

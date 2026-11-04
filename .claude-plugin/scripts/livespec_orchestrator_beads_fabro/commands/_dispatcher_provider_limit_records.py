"""The two appendable records one provider-limit release writes.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) gives the release a fixed order, and the first two steps are
records: "(1) record the hold that failure observed, scoped and keyed as the
matching signature declares; (2) journal one `provider-limit-release` record
naming the work-item, run id, factory, failing node attempt, matched cause,
scope and hold key, the candidate identity that failed, and the preserved-work
reference the release observed (the published head or preservation ref) or its
confirmed absence".

PURE. `_dispatcher_provider_limit_classify` decides, this renders, and
`_dispatcher_provider_limit_release` performs -- the same
decide/record/perform split `_acp_failure_classifier` / `_acp_hold_records` /
`_acp_hold_ledger` take one level down, and what lets every record decision
here be exercised with no journal, no ledger and no factory.

THE HOLD IS MINTED THROUGH THE SHARED WRITER RATHER THAN ASSEMBLED HERE, which
is the same choice `_acp_factory_hold_records` makes and for the same reason:
a terminal-derived hold then reads back through `parse_hold_record` to the
very record a projected failover event produces, and its bounded expiry is the
one `HOLD_INTERVAL` both valves share rather than a second interval that could
drift. The writer takes no clock, so expiry is computed from the occurrence it
is handed and from nothing else.

THE EVIDENCE ID IS THE RELEASE KEY, AND THAT IS WHAT MAKES REPLAY IDEMPOTENT.
`observation_id` digests the evidence plus the scope it lands on; the evidence
here is the `factory:run:node attempt` triple the clause keys replay by, so
re-deriving the record from the same terminal reproduces the identical id and
`ingest_hold_observation`'s first-write-wins dedupe declines it. The clause's
"without refreshing the original hold expiry" therefore falls out of the id
rather than out of a rule a replay has to remember -- the same argument
`_acp_hold_ledger` makes for its forward fold.

EVERY KEY IS WRITTEN ON BOTH ARMS, NULLS INCLUDED. An omitted key is what a
record from a build predating this clause looks like, so a reader could not
tell "this release rested on the legacy posture" from "this record was minted
before causes were named". That is why the legacy arm writes an explicit null
cause, scope and hold key beside the `legacy_provider` it did measure, instead
of leaving a reader to infer the posture from absent fields.
"""

from __future__ import annotations

from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_factory_hold_records import (
    AUDIT_REFERENCE_KEY,
    FACTORY_EVIDENCE_KIND,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import hold_observation_record
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)

__all__: list[str] = [
    "PROVIDER_LIMIT_RELEASE_STAGE",
    "HoldEvidence",
    "provider_limit_hold_record",
    "provider_limit_release_record",
]

# The journal stage a provider-limit release appends. One literal, shared by
# the producer here and every reader, exactly as `STALL_RELEASE_STAGE` is --
# and the name the clause itself uses, because the "released for recovery"
# paragraph keys recovery routing on finding this very stage.
PROVIDER_LIMIT_RELEASE_STAGE = "provider-limit-release"


class HoldEvidence(Protocol):
    """What a terminal-derived hold needs of the attempt it is derived from.

    Both a release and a reclassified turn satisfy it, so one record builder
    serves a hold minted by a release and a hold minted by a turn that ended
    nothing -- which is what lets the two derive the identical observation id.
    """

    @property
    def matched(self) -> AcpAvailabilityFailure | None:
        """The typed verdict the hold is scoped by, or `None` on the legacy posture."""
        ...

    @property
    def node_attempt(self) -> str:
        """The failing node attempt."""
        ...

    @property
    def release_key(self) -> str:
        """The `factory:run:node attempt` triple the hold's evidence id is."""
        ...


def provider_limit_release_record(
    *, release: ProviderLimitRelease, work_item_id: str
) -> dict[str, object]:
    """The one release line this terminal journals.

    `release_key` is carried rather than left to be re-joined from the three
    fields beside it: a replay compares one value, and two surfaces splitting
    the triple on different separators is how they come to disagree about
    whether they are looking at the same release.
    """
    matched = release.matched
    executed = release.executed
    return {
        "stage": PROVIDER_LIMIT_RELEASE_STAGE,
        "work_item_id": work_item_id,
        "run_id": release.run_id,
        "factory": release.factory,
        "node_attempt": release.node_attempt,
        "source": release.source,
        "cause": None if matched is None else matched.cause,
        "scope": None if matched is None else matched.scope,
        "hold_key": None if matched is None else matched.hold_key,
        "failed_candidate_key": None if executed is None else executed.candidate_key,
        "failed_availability_key": None if executed is None else executed.availability_key,
        "legacy_provider": release.legacy_provider,
        "recovery_source": release.recovery_source,
        "release_key": release.release_key,
    }


def provider_limit_hold_record(
    *, release: HoldEvidence, work_item_id: str, occurred_at: str
) -> dict[str, object] | str | None:
    """The hold this release observed, a refusal naming what is wrong, or `None`.

    The three answers are deliberately distinct, because they owe different
    treatments. A record is appended. A REFUSAL is surfaced and nothing is
    appended -- the writer's own refusal is returned rather than swallowed,
    because a line whose occurrence nobody can read carries no bounded expiry
    and would stand until an operator cleared it by hand. And `None` is the
    legacy posture, where no entitlement was recorded and so there is nothing a
    typed hold could be scoped by; minting one would name an entitlement
    nobody declared, which is the one thing the clause's "without inventing a
    candidate identity" forbids.

    The line carries the ORDINARY v1 observation plus the factory run it was
    derived from, exactly as `factory_hold_observation_record` does, because
    "Dispatch journals MAY record audit references but MUST NOT be the sole
    authority for holds": a reader of the journal is pointed back at the record
    this one can be re-derived from rather than left holding the only copy.
    """
    matched = release.matched
    if matched is None:
        return None
    record = hold_observation_record(
        failure=matched,
        evidence_kind=FACTORY_EVIDENCE_KIND,
        evidence_id=release.release_key,
        occurred_at=occurred_at,
        work_item_id=work_item_id,
        node=release.node_attempt,
    )
    if isinstance(record, str):
        return record
    return {**record, AUDIT_REFERENCE_KEY: release.release_key}

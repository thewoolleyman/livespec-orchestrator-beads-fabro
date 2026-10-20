"""The two appendable records a provider-limit release writes.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) orders the release: "(1) record the hold that failure observed,
scoped and keyed as the matching signature declares; (2) journal one
`provider-limit-release` record naming the work-item, run id, factory, failing
node attempt, matched cause, scope and hold key, the candidate identity that
failed, and the preserved-work reference the release observed ... or its
confirmed absence".

THE FAILED CANDIDATE IDENTITY AND THE HOLD KEY ARE DIFFERENT FIELDS, AND THAT
IS THE POINT OF THE FIRST TEST. A quota signature is domain-scoped, so the
typed verdict deliberately carries NO `candidate_key` -- the hold parser
refuses a domain record that names one -- while the clause still requires the
record to name "the candidate identity that failed". So the record reads the
entitlement off the EXECUTED candidate and the hold key off the VERDICT, and a
record that filled the candidate field from the verdict would report every
domain release as having run no candidate at all.

THE HOLD IS MINTED THROUGH THE SHARED WRITER, never assembled here. That is
what makes a terminal-derived hold read back through `parse_hold_record` to
the same schema-v1 record a projected failover event produces, and what keeps
its bounded expiry on the one `HOLD_INTERVAL` both valves share.

ITS OBSERVATION ID DIGESTS THE RELEASE KEY, which is what makes replay
idempotent without anything having to remember that it should be: the id is a
digest of the evidence plus the scope it lands on, the evidence here is the
`factory:run:node attempt` triple the clause keys replay by, and
`ingest_hold_observation` is first-write-wins. So a replay of one interrupted
release reproduces the identical id and cannot refresh the stored expiry.

THE LEGACY ARM MINTS NO HOLD AT ALL, and the last test is the control for it.
An identity-less adapter records no entitlement, so there is nothing a typed
record could be scoped by; the existing legacy provider observation covers it.
A builder that returned a hold there would mint an entitlement nobody declared.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_SCHEMA_VERSION,
    HOLD_STAGE,
    parse_hold_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitAttempt,
    classified_release,
    provider_limit_signal,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records"
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_provider_limit_records.py"
)

_SESSION_LIMIT = "You have hit your session limit, resets 7:20pm (UTC)"
_RUN = "01M52R2WND7Y"
_OCCURRED = "2026-10-16T19:20:00Z"
_PRESERVED = f"refs/heads/needs-human/{_RUN}"

_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key="claude-primary",
    availability_key="anthropic-team",
)

_DECLARED_QUOTA = {
    "source": "protocol.message",
    "cause": "quota",
    "scope": "availability-domain",
    "all_literals": ["hit your session limit"],
}


def _signatures(*, declared: dict[str, object]) -> Any:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures"
    )
    parsed = module.parse_availability_signatures(value=[declared], key="probe")
    assert not isinstance(parsed, str), parsed
    return parsed


def _rendered(*, identity: AcpCandidateIdentity | None, declared: dict[str, object] | None) -> Any:
    return RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="claude-code-acp", args=(), env={}),
            identity=identity,
            signatures=() if declared is None else _signatures(declared=declared),
        ),
        builtin=False,
    )


def _release(*, usage_limit: bool, rendered: Any) -> Any:
    """One release, produced by the committed decision rather than constructed.

    Built through `classified_release` on purpose: these records exist to
    describe what that decision reached, so a hand-built release value could
    drift from every release the Dispatcher can actually produce.
    """
    failure = FabroFailureDetail(
        cause=_SESSION_LIMIT,
        category="transient_infra",
        signature="implement|transient_infra|acp turn failed",
        provider_usage_limit=usage_limit,
        provider_usage_limit_provider="anthropic" if usage_limit else None,
    )
    return classified_release(
        attempt=ProviderLimitAttempt(
            signal=provider_limit_signal(failure=failure), failure=failure
        ),
        rendered=rendered,
        node_attempt="implement",
        factory="hp",
        run_id=_RUN,
        recovery_source=_PRESERVED,
    )


def _eligible_release() -> Any:
    release = _release(
        usage_limit=True, rendered=_rendered(identity=_IDENTITY, declared=_DECLARED_QUOTA)
    )
    assert release is not None
    assert release.matched is not None
    return release


def test_the_release_record_names_every_field_the_clause_enumerates() -> None:
    """All nine named facts, with the entitlement and the hold key kept apart."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    record = module.provider_limit_release_record(
        release=_eligible_release(), work_item_id="bd-ib-6itdjz"
    )

    assert record["stage"] == module.PROVIDER_LIMIT_RELEASE_STAGE
    assert record["stage"] == "provider-limit-release"
    assert record["work_item_id"] == "bd-ib-6itdjz"
    assert record["run_id"] == _RUN
    assert record["factory"] == "hp"
    assert record["node_attempt"] == "implement"
    assert record["cause"] == "quota"
    assert record["scope"] == "availability-domain"
    assert record["hold_key"] == "anthropic-team"
    # The entitlement that FAILED, read off the executed candidate. A
    # domain-scoped verdict carries no candidate key, so filling this from the
    # verdict would report every domain release as having run no candidate.
    assert record["failed_candidate_key"] == "claude-primary"
    assert record["failed_availability_key"] == "anthropic-team"
    assert record["recovery_source"] == _PRESERVED
    # The triple replay is keyed by, carried so a replay compares one value
    # rather than re-joining three.
    assert record["release_key"] == f"hp:{_RUN}:implement"


def test_the_hold_record_reads_back_as_the_schema_v1_hold_it_mirrors() -> None:
    """Minted through the shared writer, so it parses as an ordinary v1 record."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    record = module.provider_limit_hold_record(
        release=_eligible_release(), work_item_id="bd-ib-6itdjz", occurred_at=_OCCURRED
    )

    assert isinstance(record, dict), record
    assert record["stage"] == HOLD_STAGE
    assert record["schema_version"] == HOLD_SCHEMA_VERSION
    parsed = parse_hold_record(record=record)
    assert not isinstance(parsed, str), parsed
    # Scoped and keyed as the matching signature declares.
    assert parsed.scope == "availability-domain"
    assert parsed.hold_key == "anthropic-team"
    assert parsed.candidate_key is None
    assert parsed.cause == "quota"
    # Bounded expiry derived from the OCCURRENCE, on the shared interval.
    assert parsed.occurred_at == _OCCURRED
    assert parsed.expires_at == "2026-10-16T19:35:00Z"


def test_the_hold_observation_id_is_stable_across_a_replay() -> None:
    """Replay idempotence falls out of the id, not out of a rule to remember.

    Two independent builds of the same release mint the identical observation
    id, because the id digests the `factory:run:node attempt` evidence the
    clause keys replay by -- so `ingest_hold_observation`'s first-write-wins
    dedupe cannot be defeated by re-deriving the record, and the stored expiry
    cannot be pushed forward by looking again.
    """
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    first = module.provider_limit_hold_record(
        release=_eligible_release(), work_item_id="bd-ib-6itdjz", occurred_at=_OCCURRED
    )
    # A LATER occurrence, which is what a replay minutes afterwards would hand
    # it: the id must not move, or the dedupe would miss and the hold would be
    # re-minted with a fresh fifteen minutes.
    later = module.provider_limit_hold_record(
        release=_eligible_release(), work_item_id="bd-ib-6itdjz", occurred_at="2026-10-16T19:29:00Z"
    )

    assert isinstance(first, dict)
    assert isinstance(later, dict)
    assert first["observation_id"] == later["observation_id"]
    # The evidence IS the release key, so the audit reference points a reader
    # back at the factory run the record can be re-derived from.
    assert first["evidence_id"] == f"hp:{_RUN}:implement"


def test_an_unreadable_occurrence_is_refused_rather_than_recorded() -> None:
    """The writer's own refusal is returned, not swallowed into a record.

    A hold whose occurrence nobody can read carries no bounded expiry, so it
    would stand until an operator cleared it by hand.
    """
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    refusal = module.provider_limit_hold_record(
        release=_eligible_release(), work_item_id="bd-ib-6itdjz", occurred_at="last Tuesday"
    )

    assert isinstance(refusal, str)
    assert "last Tuesday" in refusal


def test_the_legacy_arm_mints_no_typed_hold_but_still_records_its_release() -> None:
    """The control: no entitlement was measured, so no typed record is written."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)
    release = _release(usage_limit=True, rendered=_rendered(identity=None, declared=None))
    assert release is not None
    assert release.matched is None

    assert (
        module.provider_limit_hold_record(
            release=release, work_item_id="bd-ib-6itdjz", occurred_at=_OCCURRED
        )
        is None
    )

    record = module.provider_limit_release_record(release=release, work_item_id="bd-ib-6itdjz")

    # The release is still journaled, and says outright that it rests on the
    # legacy posture rather than on a matched signature -- so a reader is never
    # left inferring a missing cause from absent keys.
    assert record["stage"] == "provider-limit-release"
    assert record["cause"] is None
    assert record["scope"] is None
    assert record["hold_key"] is None
    assert record["legacy_provider"] == "anthropic"
    assert record["failed_candidate_key"] is None
    assert record["failed_availability_key"] is None
    assert record["recovery_source"] == _PRESERVED

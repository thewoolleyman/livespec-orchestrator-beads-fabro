"""The versioned observed-availability hold, from minting to retirement.

Binds the hold half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -- the schema-v1 record, the
unknown-version preservation rule, coverage by domain and by exact
identity pair, the legacy compatibility blanket, and the three
retirement routes -- together with the two Scenario 127 scenarios that
govern them: "Shared and distinct identities scope holds across nodes"
and "A successful fallback still records the failed primary hold and
warning".

THREE CONTROLS CARRY MOST OF THE WEIGHT, because each is a claim that an
almost-correct implementation would get backwards:

- Re-ingesting the same evidence must neither duplicate the record nor
  PUSH ITS EXPIRY FORWARD. The second half is the one that bites: a
  dedupe written as "replace the stored record" passes a duplicate-count
  assertion and still refreshes the hold on every reconciliation pass.
- A successful FALLBACK must not clear the primary it fell back from,
  even though the run as a whole succeeded.
- An unknown `schema_version` must be PRESERVED and surfaced, not
  dropped and not read on v1's field meanings.

Everything is HERMETIC: journals are built in `tmp_path`, nothing
launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NEW_MODULES = ("_acp_hold_records", "_acp_hold_coverage", "_acp_hold_ledger")

_OCCURRED = "2026-09-11T12:00:00Z"
_BEFORE = "2026-09-11T11:59:00Z"
_WITHIN = "2026-09-11T12:10:00Z"
_AFTER_EXPIRY = "2026-09-11T12:20:00Z"


def _modules() -> dict[str, Any]:
    """Import the slice's modules, proving each file exists first."""
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"
    return {name: importlib.import_module(f"{_PACKAGE}.{name}") for name in _NEW_MODULES}


def _failure(*, scope: str, hold_key: str, candidate_key: str | None, cause: str = "quota") -> Any:
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    return classifier.AcpAvailabilityFailure(
        cause=cause,
        scope=scope,
        hold_key=hold_key,
        availability_key=hold_key,
        candidate_key=candidate_key,
        source="protocol.message",
    )


def _domain_failure() -> Any:
    return _failure(scope="availability-domain", hold_key="codex", candidate_key=None)


def _candidate_failure(*, candidate_key: str = "gpt-5-5") -> Any:
    return _failure(
        scope="candidate", hold_key="codex", candidate_key=candidate_key, cause="model_unsupported"
    )


def _candidate(*, identity: Any | None, signatures: tuple[Any, ...] = ()) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
        signatures=signatures,
    )


def _identity(*, availability_key: str = "codex", candidate_key: str = "gpt-5-5") -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    return schema.AcpCandidateIdentity(
        display_name="a candidate",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _write(*, path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


class _Recorder:
    """A journal that keeps what it was told to append."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_a_v1_observation_carries_every_enumerated_field() -> None:
    """The record shape is the contract's own list, and expiry is bounded."""
    records = _modules()["_acp_hold_records"]
    built = records.hold_observation_record(
        failure=_candidate_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1:implement:0",
        occurred_at=_OCCURRED,
        work_item_id="bd-ib-5ltgny",
        node="implement",
    )
    assert isinstance(built, dict)
    assert built["schema_version"] == records.HOLD_SCHEMA_VERSION == 1
    assert built["scope"] == "candidate"
    assert built["hold_key"] == "codex"
    assert built["candidate_key"] == "gpt-5-5"
    assert built["occurred_at"] == _OCCURRED
    # Bounded, and derived from the OCCURRENCE, not from any clock the
    # builder could have read -- it is handed none.
    assert built["expires_at"] == "2026-09-11T12:15:00Z"
    assert isinstance(built["observation_id"], str)
    assert str(built["observation_id"]).startswith("acpobs-")


def test_only_an_actual_attempt_can_mint_a_hold() -> None:
    """No spelling of a probe, catalog or reset claim is an accepted evidence kind."""
    records = _modules()["_acp_hold_records"]
    for kind in ("credential-probe", "catalog", "predicted-health", "provider-reset-claim"):
        refusal = records.hold_observation_record(
            failure=_domain_failure(),
            evidence_kind=kind,
            evidence_id="anything",
            occurred_at=_OCCURRED,
            work_item_id="bd-ib-5ltgny",
            node="implement",
        )
        assert isinstance(refusal, str)
        assert kind in refusal
    blank = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="acp-failover-event",
        evidence_id="   ",
        occurred_at=_OCCURRED,
        work_item_id="bd-ib-5ltgny",
        node="implement",
    )
    assert isinstance(blank, str)
    unreadable = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="acp-failover-event",
        evidence_id="event-1",
        occurred_at="the day before yesterday",
        work_item_id="bd-ib-5ltgny",
        node="implement",
    )
    assert isinstance(unreadable, str)


def test_the_observation_id_is_stable_per_evidence_and_per_scope() -> None:
    """Same evidence reproduces the id; a different scope gets its own."""
    records = _modules()["_acp_hold_records"]
    first = records.observation_id(
        evidence_kind="acp-failover-event", evidence_id="event-1", failure=_domain_failure()
    )
    again = records.observation_id(
        evidence_kind="acp-failover-event", evidence_id="event-1", failure=_domain_failure()
    )
    assert first == again
    # One event can land on both a domain and a candidate record; keying
    # on the evidence alone would collapse them into one.
    other_scope = records.observation_id(
        evidence_kind="acp-failover-event", evidence_id="event-1", failure=_candidate_failure()
    )
    assert other_scope != first
    other_event = records.observation_id(
        evidence_kind="acp-failover-event", evidence_id="event-2", failure=_domain_failure()
    )
    assert other_event != first


def test_a_malformed_or_unknown_version_record_is_unobservable_not_v1() -> None:
    """Every rejected shape is reported as unreadable rather than guessed at."""
    records = _modules()["_acp_hold_records"]
    good = records.hold_observation_record(
        failure=_candidate_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(good, dict)
    assert isinstance(records.parse_hold_record(record=good), records.AcpAvailabilityHold)
    # A v2 record spelling every v1 field identically is STILL not v1.
    assert isinstance(records.parse_hold_record(record={**good, "schema_version": 2}), str)
    assert isinstance(records.parse_hold_record(record={**good, "scope": "everything"}), str)
    assert isinstance(records.parse_hold_record(record={**good, "hold_key": "  "}), str)
    assert isinstance(records.parse_hold_record(record={**good, "occurred_at": "soon"}), str)
    assert isinstance(records.parse_hold_record(record={**good, "candidate_key": None}), str)
    domain = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(domain, dict)
    assert isinstance(records.parse_hold_record(record=domain), records.AcpAvailabilityHold)
    # A domain record naming a candidate is a shape nobody writes, and it
    # is refused rather than silently narrowed.
    assert isinstance(records.parse_hold_record(record={**domain, "candidate_key": "x"}), str)


def test_expiry_is_read_off_the_record_and_an_unreadable_clock_holds() -> None:
    """A hold lapses at its own bounded expiry; an unreadable now keeps it."""
    records = _modules()["_acp_hold_records"]
    built = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(built, dict)
    hold = records.parse_hold_record(record=built)
    assert isinstance(hold, records.AcpAvailabilityHold)
    assert not records.hold_expired(hold=hold, now_iso=_WITHIN)
    assert records.hold_expired(hold=hold, now_iso=_AFTER_EXPIRY)
    # Dropping a live provider hold because the CALLER's clock could not
    # be read would send work straight at the outage.
    assert not records.hold_expired(hold=hold, now_iso="not a time")
    assert hold.target == ("availability-domain", "codex", None)


def test_domain_holds_cover_a_declared_override_and_candidate_holds_do_not() -> None:
    """Scenario 127: domain membership is the availability key plus its overrides."""
    modules = _modules()
    coverage = modules["_acp_hold_coverage"]
    records = modules["_acp_hold_records"]
    signatures = importlib.import_module(f"{_PACKAGE}._acp_candidate_signatures")
    pooled = signatures.AcpAvailabilitySignature(
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("pool",),
        hold_key="shared-router-pool",
    )
    # A CANDIDATE-scoped signature contributes no domain key: the grammar
    # refuses a `hold_key` on one, so it has none to contribute.
    scoped = signatures.AcpAvailabilitySignature(
        source="protocol.message",
        cause="model_unsupported",
        scope="candidate",
        all_literals=("gone",),
    )
    candidate = _candidate(identity=_identity(), signatures=(pooled, scoped))
    assert coverage.candidate_domain_keys(candidate=candidate) == frozenset(
        {"codex", "shared-router-pool"}
    )
    assert coverage.candidate_domain_keys(candidate=_candidate(identity=None)) == frozenset()

    def hold_of(*, failure: Any) -> Any:
        built = records.hold_observation_record(
            failure=failure,
            evidence_kind="candidate-attempt",
            evidence_id=f"run-{failure.scope}-{failure.hold_key}-{failure.candidate_key}",
            occurred_at=_OCCURRED,
            work_item_id="i",
            node="implement",
        )
        assert isinstance(built, dict)
        parsed = records.parse_hold_record(record=built)
        assert isinstance(parsed, records.AcpAvailabilityHold)
        return parsed

    pool_hold = hold_of(
        failure=_failure(
            scope="availability-domain", hold_key="shared-router-pool", candidate_key=None
        )
    )
    assert coverage.hold_covers_candidate(hold=pool_hold, candidate=candidate)
    unrelated = hold_of(
        failure=_failure(scope="availability-domain", hold_key="anthropic", candidate_key=None)
    )
    assert not coverage.hold_covers_candidate(hold=unrelated, candidate=candidate)
    exact = hold_of(failure=_candidate_failure())
    assert coverage.hold_covers_candidate(hold=exact, candidate=candidate)
    # Same domain, different candidate key: covers nothing here.
    sibling = hold_of(failure=_candidate_failure(candidate_key="gpt-5-5-mini"))
    assert not coverage.hold_covers_candidate(hold=sibling, candidate=candidate)
    # A typed record never reaches the identity-less legacy candidate.
    assert not coverage.hold_covers_candidate(hold=pool_hold, candidate=_candidate(identity=None))


def test_the_legacy_blanket_covers_built_ins_and_legacy_adapters_only() -> None:
    """A legacy vendor record must not broaden onto an unrelated identity."""
    modules = _modules()
    coverage = modules["_acp_hold_coverage"]
    records = modules["_acp_hold_records"]
    legacy_adapter = _candidate(identity=None)
    builtin = _candidate(identity=_identity(availability_key="codex", candidate_key="builtin-x"))
    chosen = _candidate(identity=_identity(availability_key="codex", candidate_key="mine"))
    assert coverage.legacy_record_covers_candidate(
        provider="codex", candidate=legacy_adapter, builtin=False
    )
    assert coverage.legacy_record_covers_candidate(
        provider="codex", candidate=builtin, builtin=True
    )
    assert not coverage.legacy_record_covers_candidate(
        provider="anthropic", candidate=builtin, builtin=True
    )
    # An operator who chose the vendor's own word as their key has NOT
    # opted into the vendor's legacy blanket; identity is never inferred
    # from how a key is spelled.
    assert not coverage.legacy_record_covers_candidate(
        provider="codex", candidate=chosen, builtin=False
    )
    built = records.hold_observation_record(
        failure=_candidate_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(built, dict)
    typed = records.parse_hold_record(record=built)
    assert isinstance(typed, records.AcpAvailabilityHold)
    assert coverage.legacy_yields_to_typed(
        chain_executed=True, candidate=_candidate(identity=_identity()), holds=(typed,)
    )
    # No chain executed means no typed evidence to prefer.
    assert not coverage.legacy_yields_to_typed(
        chain_executed=False, candidate=_candidate(identity=_identity()), holds=(typed,)
    )
    # DOMAIN evidence says the entitlement is spent, not that this
    # identity was tried, so it does not displace legacy attribution.
    domain_built = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-2",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(domain_built, dict)
    domain_hold = records.parse_hold_record(record=domain_built)
    assert isinstance(domain_hold, records.AcpAvailabilityHold)
    assert not coverage.legacy_yields_to_typed(
        chain_executed=True, candidate=_candidate(identity=_identity()), holds=(domain_hold,)
    )


def test_repeated_ingestion_neither_duplicates_nor_refreshes_expiry(tmp_path: Path) -> None:
    """The load-bearing idempotence control, asserted on the expiry too."""
    modules = _modules()
    ledger_module = modules["_acp_hold_ledger"]
    records = modules["_acp_hold_records"]
    observation = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="acp-failover-event",
        evidence_id="event-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(observation, dict)
    # A SECOND ingestion at a later occurrence time, as a replayed
    # projection would produce if it recomputed expiry from `now`.
    later = {**observation, "occurred_at": _WITHIN, "expires_at": "2026-09-11T12:25:00Z"}
    path = _write(path=tmp_path / "journal.jsonl", records=(observation, later))
    ledger = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert len(ledger.holds) == 1
    # FIRST write wins: the stored expiry is the original one, so a
    # replay cannot push the hold forward.
    assert ledger.holds[0].expires_at == "2026-09-11T12:15:00Z"
    recorder = _Recorder()
    assert not ledger_module.ingest_hold_observation(
        record=dict(observation), ledger=ledger, journal=recorder
    )
    assert recorder.records == []
    fresh = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="acp-failover-event",
        evidence_id="event-2",
        occurred_at=_WITHIN,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(fresh, dict)
    assert ledger_module.ingest_hold_observation(
        record=dict(fresh), ledger=ledger, journal=recorder
    )
    assert len(recorder.records) == 1
    # A record with no id at all is written rather than silently swallowed.
    assert ledger_module.ingest_hold_observation(
        record={"stage": records.HOLD_STAGE}, ledger=ledger, journal=recorder
    )


def test_the_ledger_preserves_unknown_versions_and_survives_a_torn_line(
    tmp_path: Path,
) -> None:
    """An unknown version rides out intact; a truncated line is not fatal."""
    modules = _modules()
    ledger_module = modules["_acp_hold_ledger"]
    records = modules["_acp_hold_records"]
    observation = records.hold_observation_record(
        failure=_domain_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(observation, dict)
    future = {**observation, "schema_version": 7, "observation_id": "acpobs-future"}
    path = tmp_path / "journal.jsonl"
    _ = _write(path=path, records=(observation, future, {"stage": "unrelated"}))
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write('{"stage": "acp-avail\n')
        _ = handle.write("[1, 2, 3]\n")
    ledger = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert len(ledger.holds) == 1
    assert len(ledger.unobservable) == 1
    # PRESERVED, not reinterpreted: the raw payload rides out whole and
    # its unknown version is still 7.
    assert ledger.unobservable[0]["schema_version"] == 7
    assert ledger.unobservable[0]["observation_id"] == "acpobs-future"
    assert "acpobs-future" not in ledger.observation_ids
    assert ledger_module.read_acp_hold_ledger(journal_path=None, now_iso=_WITHIN).holds == ()
    assert (
        ledger_module.read_acp_hold_ledger(
            journal_path=tmp_path / "absent.jsonl", now_iso=_WITHIN
        ).holds
        == ()
    )


def test_expiry_and_exact_clearance_retire_a_hold(tmp_path: Path) -> None:
    """Two of the three routes, and the clearance names its exact targets."""
    modules = _modules()
    ledger_module = modules["_acp_hold_ledger"]
    records = modules["_acp_hold_records"]
    observation = records.hold_observation_record(
        failure=_candidate_failure(),
        evidence_kind="candidate-attempt",
        evidence_id="run-1",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(observation, dict)
    path = _write(path=tmp_path / "journal.jsonl", records=(observation,))
    live = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert len(live.holds) == 1
    lapsed = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_AFTER_EXPIRY)
    assert lapsed.holds == ()
    targets = ledger_module.live_holds_for_target(
        ledger=live, scope="candidate", hold_key="codex", candidate_key="gpt-5-5"
    )
    assert len(targets) == 1
    assert (
        ledger_module.live_holds_for_target(
            ledger=live, scope="candidate", hold_key="codex", candidate_key="other"
        )
        == ()
    )
    clearance = ledger_module.acp_hold_clearance_record(
        scope="candidate",
        hold_key="codex",
        candidate_key="gpt-5-5",
        reason="the account was re-entitled",
        observation_ids=tuple(hold.observation_id for hold in targets),
    )
    assert clearance["stage"] == ledger_module.CLEARED_STAGE
    # Append-only: the clearance is a NEW line and the observation stays.
    _ = _write(path=path, records=(observation, clearance))
    cleared = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert cleared.holds == ()
    assert len(cleared.observation_ids) == 1
    # A retirement line naming no ids retires nothing.
    _ = _write(
        path=path, records=(observation, {"stage": ledger_module.CLEARED_STAGE, "scope": "x"})
    )
    assert len(ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN).holds) == 1


def test_a_later_matching_success_retires_only_what_it_falsifies(tmp_path: Path) -> None:
    """Scenario 127: a successful fallback never clears its failed primary."""
    modules = _modules()
    ledger_module = modules["_acp_hold_ledger"]
    records = modules["_acp_hold_records"]

    def observed(*, failure: Any, occurred_at: str, evidence_id: str) -> dict[str, Any]:
        built = records.hold_observation_record(
            failure=failure,
            evidence_kind="candidate-attempt",
            evidence_id=evidence_id,
            occurred_at=occurred_at,
            work_item_id="i",
            node="implement",
        )
        assert isinstance(built, dict)
        return dict(built)

    primary = observed(
        failure=_candidate_failure(candidate_key="primary"),
        occurred_at=_OCCURRED,
        evidence_id="run-1:0",
    )
    domain = observed(failure=_domain_failure(), occurred_at=_OCCURRED, evidence_id="run-1:d")
    stale = observed(
        failure=_failure(scope="availability-domain", hold_key="codex", candidate_key=None),
        occurred_at=_WITHIN,
        evidence_id="run-9:d",
    )
    path = _write(path=tmp_path / "journal.jsonl", records=(primary, domain, stale))
    ledger = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert len(ledger.holds) == 3
    success = ledger_module.AcpSuccessfulAttempt(
        availability_key="codex",
        candidate_key="fallback",
        domain_keys=frozenset({"codex"}),
        started_at="2026-09-11T12:05:00Z",
    )
    retirements = ledger_module.success_retirement_records(ledger=ledger, success=success)
    retired_ids = {
        identifier
        for record in retirements
        for identifier in list(record["observation_ids"])  # pyright: ignore[reportAny]
    }
    # The same-domain success retires the older DOMAIN record...
    assert domain["observation_id"] in retired_ids
    # ...and never the primary's CANDIDATE record, though the run succeeded.
    assert primary["observation_id"] not in retired_ids
    # ...nor an observation that post-dates the attempt's own start.
    assert stale["observation_id"] not in retired_ids
    assert all(record["stage"] == ledger_module.RETIRED_STAGE for record in retirements)
    _ = _write(path=path, records=(primary, domain, stale, *retirements))
    after = ledger_module.read_acp_hold_ledger(journal_path=path, now_iso=_WITHIN)
    assert {hold.observation_id for hold in after.holds} == {
        primary["observation_id"],
        stale["observation_id"],
    }


def test_success_retirement_keys_on_the_exact_identity_and_a_readable_clock(
    tmp_path: Path,
) -> None:
    """A candidate record yields only to its own pair, and never on a bad clock."""
    modules = _modules()
    ledger_module = modules["_acp_hold_ledger"]
    records = modules["_acp_hold_records"]
    built = records.hold_observation_record(
        failure=_candidate_failure(candidate_key="primary"),
        evidence_kind="candidate-attempt",
        evidence_id="run-1:0",
        occurred_at=_OCCURRED,
        work_item_id="i",
        node="implement",
    )
    assert isinstance(built, dict)
    hold = records.parse_hold_record(record=built)
    assert isinstance(hold, records.AcpAvailabilityHold)
    same = ledger_module.AcpSuccessfulAttempt(
        availability_key="codex",
        candidate_key="primary",
        domain_keys=frozenset({"codex"}),
        started_at="2026-09-11T12:05:00Z",
    )
    assert ledger_module.retired_by_success(hold=hold, success=same)
    other = ledger_module.AcpSuccessfulAttempt(
        availability_key="anthropic",
        candidate_key="primary",
        domain_keys=frozenset({"anthropic"}),
        started_at="2026-09-11T12:05:00Z",
    )
    assert not ledger_module.retired_by_success(hold=hold, success=other)
    # An attempt already running when the outage was observed proves
    # nothing about it.
    earlier = ledger_module.AcpSuccessfulAttempt(
        availability_key="codex",
        candidate_key="primary",
        domain_keys=frozenset({"codex"}),
        started_at=_BEFORE,
    )
    assert not ledger_module.retired_by_success(hold=hold, success=earlier)
    # Retirement is the destructive direction, so an unreadable clock
    # must not be allowed to authorise one.
    unreadable = ledger_module.AcpSuccessfulAttempt(
        availability_key="codex",
        candidate_key="primary",
        domain_keys=frozenset({"codex"}),
        started_at="whenever",
    )
    assert not ledger_module.retired_by_success(hold=hold, success=unreadable)
    empty = ledger_module.read_acp_hold_ledger(journal_path=tmp_path / "none", now_iso=_WITHIN)
    assert ledger_module.success_retirement_records(ledger=empty, success=same) == ()

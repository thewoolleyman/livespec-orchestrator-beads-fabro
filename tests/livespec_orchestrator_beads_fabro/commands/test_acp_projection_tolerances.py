"""What the ACP projection readers do with input they cannot read.

The happy paths are bound by `test_acp_event_projection.py`. This module
binds the DEFENSIVE half, and it exists as its own file because every
case here shares one property that is easy to get wrong in the same way:
each malformed input has a plausible WRONG answer that looks exactly
like a correct empty result.

The three rules these cases enforce, all from `SPECIFICATION/contracts.md`
section "Factory-configurable ACP fallback priority":

- An unreadable RECORD is preserved and surfaced as unobservable, never
  dropped and never read on v1's field meanings.
- An unreadable PAYLOAD is a read failure, and "Read failure is not
  absence" -- it must refuse rather than report an empty stream.
- A retirement is the destructive direction, so an unreadable instant
  keeps the warning rather than authorising a clearance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    ACP_SIDE_EFFECT_EVENT,
    AcpEventScan,
    AcpNodeStart,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    AcpPrimaryAttempt,
    ModelFallbackWarningLedger,
    ingest_model_fallback_warning,
    newest_warning_per_node,
    primary_attempt_clears,
    primary_attempts_from_scan,
    primary_replacement_records,
    read_model_fallback_warnings,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    MODEL_FALLBACK_CLEARED_STAGE,
    MODEL_FALLBACK_STAGE,
    ModelFallbackWarning,
    parse_model_fallback_warning,
)
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    PROJECTION_FAILURE_STAGE,
    AcpProjectionFailureTarget,
    projection_failure_clearance_record,
    projection_failure_record,
    unresolved_projection_failures,
)

_OCCURRED = "2026-09-12T12:00:00Z"


def _identity(*, index: object = 0, key: str = "gpt-5-5") -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
    }


def _event(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": "ev-1",
        "occurred_at": _OCCURRED,
        "node": "implement",
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(),
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
    }
    record.update(overrides)
    return record


def _warning_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "stage": MODEL_FALLBACK_STAGE,
        "schema_version": 1,
        "warning_id": "acpwarn-1",
        "node": "implement",
        "occurred_at": _OCCURRED,
        "candidate_display_name": "display claude-haiku",
        "candidate_key": "claude-haiku",
        "availability_key": "codex",
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "event_id": "ev-1",
        "candidate_index": 1,
        "work_item_id": "bd-ib-xtgwpz",
    }
    record.update(overrides)
    return record


def _warning(**overrides: Any) -> ModelFallbackWarning:
    parsed = parse_model_fallback_warning(record=_warning_record(**overrides))
    assert isinstance(parsed, ModelFallbackWarning)
    return parsed


def _write(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "journal.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(
    "payload",
    [
        "not an array",
        {"runs": []},
        [1, 2, 3],
        None,
    ],
)
def test_an_unreadable_payload_refuses_rather_than_reporting_an_empty_stream(
    payload: object,
) -> None:
    """Read failure is not absence, whatever shape the unreadable payload took."""
    assert isinstance(scan_acp_events(payload=payload), str)


def test_the_envelope_form_and_the_bare_array_form_read_identically() -> None:
    """Both transports are accepted, so a transport change is not a false failure."""
    bare = scan_acp_events(payload=[_event()])
    wrapped = scan_acp_events(payload={"events": [_event()]})
    assert isinstance(bare, AcpEventScan)
    assert isinstance(wrapped, AcpEventScan)
    assert [event.event_id for event in bare.events] == [event.event_id for event in wrapped.events]


def test_the_side_effect_ledger_and_the_native_failover_are_never_projected() -> None:
    """ "`agent.acp.side_effect` is engine-internal evidence and is not a hold source"."""
    scan = scan_acp_events(
        payload=[
            {"type": ACP_SIDE_EFFECT_EVENT, "schema_version": 1, "node": "pr"},
            {"type": "agent.failover", "schema_version": 1, "node": "pr"},
        ]
    )
    assert isinstance(scan, AcpEventScan)
    assert (scan.events, scan.unobservable, scan.starts) == ((), (), ())


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_id": ""},
        {"node": None},
        {"scope": "not-a-scope"},
        {"from": "not an object"},
        {"from": _identity(index=-1)},
        {"from": _identity(index=True)},
        {"from": {"candidate_index": 0, "display_name": "d", "candidate_key": "k"}},
    ],
)
def test_a_v1_event_missing_a_required_field_is_preserved_as_unobservable(
    overrides: dict[str, Any],
) -> None:
    """An unreadable v1 record is SURFACED, exactly as an unknown version is."""
    scan = scan_acp_events(payload=[_event(**overrides)])
    assert isinstance(scan, AcpEventScan)
    assert scan.events == ()
    assert len(scan.unobservable) == 1


def test_a_malformed_to_side_reads_as_an_exhaustion_rather_than_a_transition() -> None:
    """An unreadable `to` cannot be trusted to name a candidate that RAN."""
    scan = scan_acp_events(payload=[_event(to={"candidate_index": 1})])
    assert isinstance(scan, AcpEventScan)
    assert scan.events[0].to_candidate_index is None
    assert scan.events[0].executed_non_primary is False


def test_an_unreadable_node_visit_counter_still_yields_a_projectable_event() -> None:
    """Counters are REPORTED, so a missing one must not cost the event its hold."""
    scan = scan_acp_events(payload=[_event(node_visit="third", engine_attempt=None)])
    assert isinstance(scan, AcpEventScan)
    assert (scan.events[0].node_visit, scan.events[0].engine_attempt) == (0, 0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"candidate_index": None},
        {"candidate_index": True},
        {"node": ""},
        {"occurred_at": None},
        {"primary_generation": None},
    ],
)
def test_a_started_event_without_the_additive_chain_fields_is_not_read(
    overrides: dict[str, Any],
) -> None:
    """A pre-chain start says nothing about WHICH candidate ran, so it clears nothing."""
    record: dict[str, Any] = {
        "type": "agent.acp.started",
        "node": "implement",
        "candidate_index": 0,
        "occurred_at": _OCCURRED,
        "primary_generation": "gen-a",
    }
    record.update(overrides)
    scan = scan_acp_events(payload=[record])
    assert isinstance(scan, AcpEventScan)
    assert scan.starts == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 7},
        {"node": ""},
        {"occurred_at": "the other day"},
        {"candidate_index": "first"},
        {"candidate_index": True},
        {"event_id": ""},
    ],
)
def test_an_unreadable_warning_record_is_refused_with_a_naming_reason(
    overrides: dict[str, Any],
) -> None:
    """Every refusal names the field, so an operator can repair the record."""
    refusal = parse_model_fallback_warning(record=_warning_record(**overrides))
    assert isinstance(refusal, str)
    assert refusal


def test_a_warning_record_with_no_work_item_id_still_parses() -> None:
    """The work-item is provenance, not identity: its absence loses no warning."""
    record = _warning_record()
    del record["work_item_id"]
    parsed = parse_model_fallback_warning(record=record)
    assert isinstance(parsed, ModelFallbackWarning)
    assert parsed.work_item_id == ""


def test_an_unreadable_warning_rides_out_on_unobservable_rather_than_vanishing(
    tmp_path: Path,
) -> None:
    """Preserved and surfaced, so a schema change is visible instead of silent."""
    path = _write(tmp_path=tmp_path, records=(_warning_record(schema_version=9),))
    ledger = read_model_fallback_warnings(journal_path=path)
    assert ledger.warnings == ()
    assert ledger.unobservable[0]["schema_version"] == 9


def test_a_retirement_line_naming_no_warning_ids_retires_nothing(tmp_path: Path) -> None:
    """A malformed clearance must not silently retire the whole node."""
    path = _write(
        tmp_path=tmp_path,
        records=(
            _warning_record(),
            {"stage": MODEL_FALLBACK_CLEARED_STAGE, "warning_ids": "acpwarn-1"},
        ),
    )
    assert len(read_model_fallback_warnings(journal_path=path).warnings) == 1


def test_re_ingesting_a_warning_the_journal_already_carries_appends_nothing() -> None:
    """Dedupe is against every id EVER seen, not against the live set."""
    appended: list[dict[str, object]] = []

    class _Journal:
        def append(self, *, record: dict[str, object]) -> None:
            appended.append(record)

    ledger = ModelFallbackWarningLedger(
        warnings=(), unobservable=(), warning_ids=frozenset({"acpwarn-1"})
    )
    journal = _Journal()
    assert (
        ingest_model_fallback_warning(record=_warning_record(), ledger=ledger, journal=journal)
        is False
    )
    assert appended == []
    # The control: a warning the journal has never carried IS appended, so
    # the assertion above measures dedupe rather than a journal that writes
    # nothing at all.
    fresh = _warning_record(warning_id="acpwarn-2")
    assert ingest_model_fallback_warning(record=fresh, ledger=ledger, journal=journal) is True
    assert appended == [fresh]


def test_the_newest_warning_per_node_breaks_an_equal_instant_on_the_warning_id() -> None:
    """Two warnings in one second must still order identically on every machine."""
    first = _warning(warning_id="acpwarn-a")
    second = _warning(warning_id="acpwarn-b")
    ledger = ModelFallbackWarningLedger(
        warnings=(second, first), unobservable=(), warning_ids=frozenset()
    )
    assert newest_warning_per_node(ledger=ledger)["implement"].warning_id == "acpwarn-b"


@pytest.mark.parametrize(
    ("attempt", "reason"),
    [
        (
            AcpPrimaryAttempt(
                node="implement",
                primary_generation="gen-a",
                started_at="2026-09-12T12:05:00Z",
                executed=False,
                succeeded=True,
            ),
            "a credential probe or unexecuted preflight selection",
        ),
        (
            AcpPrimaryAttempt(
                node="implement",
                primary_generation="gen-a",
                started_at="2026-09-12T12:05:00Z",
                executed=True,
                succeeded=False,
            ),
            "an attempt that ran and did not succeed",
        ),
        (
            AcpPrimaryAttempt(
                node="review",
                primary_generation="gen-a",
                started_at="2026-09-12T12:05:00Z",
                executed=True,
                succeeded=True,
            ),
            "an unrelated node's success",
        ),
        (
            AcpPrimaryAttempt(
                node="implement",
                primary_generation="gen-replaced",
                started_at="2026-09-12T12:05:00Z",
                executed=True,
                succeeded=True,
            ),
            "a different primary generation",
        ),
        (
            AcpPrimaryAttempt(
                node="implement",
                primary_generation="gen-a",
                started_at="2026-09-12T11:55:00Z",
                executed=True,
                succeeded=True,
            ),
            "an older concurrent attempt",
        ),
        (
            AcpPrimaryAttempt(
                node="implement",
                primary_generation="gen-a",
                started_at="whenever",
                executed=True,
                succeeded=True,
            ),
            "an unreadable start instant",
        ),
    ],
)
def test_the_near_misses_the_clearance_rule_enumerates_all_fail_to_clear(
    attempt: AcpPrimaryAttempt, reason: str
) -> None:
    """Each arm of the conjunction refuses a different way of clearing on no evidence."""
    assert primary_attempt_clears(warning=_warning(), attempt=attempt) is False, reason


def test_an_unreadable_warning_instant_also_keeps_the_warning_standing() -> None:
    """Retirement is destructive, so an unreadable clock never authorises one."""
    attempt = AcpPrimaryAttempt(
        node="implement",
        primary_generation="gen-a",
        started_at="2026-09-12T12:05:00Z",
        executed=True,
        succeeded=True,
    )
    assert primary_attempt_clears(warning=_warning(occurred_at=_OCCURRED), attempt=attempt) is True


def test_a_node_absent_from_the_current_generations_is_never_superseded() -> None:
    """An unreadable configuration must not retire every warning at once."""
    ledger = ModelFallbackWarningLedger(
        warnings=(_warning(),), unobservable=(), warning_ids=frozenset()
    )
    assert primary_replacement_records(ledger=ledger, primary_generations={}) == ()


def test_a_non_primary_start_is_reported_as_an_executed_attempt_that_cannot_clear() -> None:
    """ "Unrelated success ... cannot clear it", arriving as data rather than a case."""
    scan = AcpEventScan(
        events=(),
        unobservable=(),
        starts=(
            AcpNodeStart(
                node="implement",
                node_visit=2,
                candidate_index=1,
                occurred_at="2026-09-12T12:05:00Z",
                primary_generation="gen-a",
            ),
        ),
    )
    attempts = primary_attempts_from_scan(scan=scan, succeeded_nodes=frozenset({"implement"}))
    assert (attempts[0].executed, attempts[0].succeeded) == (True, False)
    assert primary_attempt_clears(warning=_warning(), attempt=attempts[0]) is False


def test_the_journal_reader_tolerates_absence_unreadability_and_junk_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One truncated line must not make a whole ledger unreadable."""
    assert journal_records(journal_path=None) == ()
    assert journal_records(journal_path=tmp_path / "missing.jsonl") == ()
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    assert journal_records(journal_path=directory) == ()
    path = tmp_path / "mixed.jsonl"
    path.write_text('{"stage": "a"}\n{truncated\n[1,2]\n', encoding="utf-8")
    assert [record["stage"] for record in journal_records(journal_path=path)] == ["a"]

    def _refuse(*_args: object, **_kwargs: object) -> str:
        raise OSError("permission denied")

    # A journal the process cannot READ reports no records rather than
    # raising through whichever ledger happened to ask for it first.
    monkeypatch.setattr(Path, "read_text", _refuse)
    assert journal_records(journal_path=path) == ()


def test_a_projection_failure_line_missing_a_field_is_not_read_as_a_fact(
    tmp_path: Path,
) -> None:
    """A line nobody can read must not stop the drain on a fact it cannot describe."""
    complete = projection_failure_record(
        target=AcpProjectionFailureTarget(
            repo="repo",
            run_id="01RUN",
            node="implement",
            factory_name="hp",
            factory_server_url="https://hp:32276",
        ),
        reason="fetch-failed",
        exit_code=True,
    )
    missing = {**complete, "factory_name": ""}
    unknown_reason = {**complete, "reason": "vibes"}
    no_fact_id = {key: value for key, value in complete.items() if key != "fact_id"}
    unrelated = {"stage": "outcome", "fact_id": "hygiene:model-fallback-projection:r:1:n"}
    path = _write(
        tmp_path=tmp_path, records=(missing, unknown_reason, no_fact_id, unrelated, complete)
    )
    unresolved = unresolved_projection_failures(journal_path=path)
    assert len(unresolved) == 1
    # A boolean exit code is refused rather than read as exit 1.
    assert unresolved[0].exit_code is None
    assert "exit n/a" in unresolved[0].summary
    assert "attempts" not in unresolved[0].summary


def test_a_clearance_naming_a_fact_id_retires_that_fact_and_nothing_else(
    tmp_path: Path,
) -> None:
    """Clearance is scoped to one id, and it carries no hold target at all."""
    target = AcpProjectionFailureTarget(
        repo="repo",
        run_id="01RUN",
        node="implement",
        factory_name="hp",
        factory_server_url="https://hp:32276",
    )
    other = AcpProjectionFailureTarget(
        repo="repo",
        run_id="01OTHER",
        node="implement",
        factory_name="hp",
        factory_server_url="https://hp:32276",
    )
    first = projection_failure_record(target=target, reason="timed-out", exit_code=124)
    second = projection_failure_record(target=other, reason="timed-out", exit_code=124)
    clearance = projection_failure_clearance_record(
        fact_id=str(first["fact_id"]), reason="the factory was decommissioned"
    )
    assert set(clearance) == {"stage", "fact_id", "reason"}
    path = _write(tmp_path=tmp_path, records=(first, second, clearance))
    remaining = unresolved_projection_failures(journal_path=path)
    assert [entry.run_id for entry in remaining] == ["01OTHER"]
    assert [record["stage"] for record in journal_records(journal_path=path)].count(
        PROJECTION_FAILURE_STAGE
    ) == 2

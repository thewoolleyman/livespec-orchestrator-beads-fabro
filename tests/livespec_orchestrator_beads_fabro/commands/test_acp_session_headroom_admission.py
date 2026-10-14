"""Admission's session-headroom filter: the reading, the floor, the records.

Binds `SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" -> "Admission filters candidates by projected Claude
session headroom", the headroom clause of the Per-node selection eligibility
predicate in section "Factory-configurable ACP fallback priority", and the
headroom arms of `SPECIFICATION/scenarios.md` Scenario 60.

THE CONTROLS THAT CARRY THE WEIGHT, each a claim an almost-correct
implementation gets backwards:

- An unobservable reading is NOT a number. Coercing it to zero reads as FULL
  headroom, which admits exactly the run the filter exists to hold, and a test
  that only checked "a reading was journaled" would pass on that.
- A floor of `0` keeps the reading AND the journal line while disabling both
  skips. An implementation that short-circuits before reading looks identical
  from the skip behaviour alone.
- A reading mints NO availability record and retires none. The provider's usage
  figure has been measured stale against its own refusals, so a reading above
  the floor is not evidence of availability -- and a hold the reading quietly
  retired would be invisible from every assertion about skipping.
- The identity journaled is a digest of the EXACT projected token. A reading
  taken against some other credential is a clean, plausible, wrong answer.

Everything is HERMETIC: no credential is read, no provider is reached, and the
usage transport is replaced by a local stub.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NEW_MODULES = (
    "_acp_session_headroom",
    "_dispatcher_session_headroom_io",
    "_dispatcher_session_headroom_records",
)

_NOW = "2026-10-14T12:00:00Z"
_ITEM_ID = "bd-ib-headroom"
_TOKEN = "sk-ant-oat01-fake-token-for-tests"


def _modules() -> dict[str, Any]:
    """Import this slice's modules, proving each file exists first."""
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"
    return {name: importlib.import_module(f"{_PACKAGE}.{name}") for name in _NEW_MODULES}


@dataclass(kw_only=True)
class _MemoryJournal:
    path: Path | None = None
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append({"at": _NOW, **record})


def _reading(*, utilization: float | None = 40.0, unobservable: str | None = None) -> Any:
    headroom = importlib.import_module(f"{_PACKAGE}._acp_session_headroom")
    return headroom.SessionHeadroomReading(
        credential_identity="claude-oauth-deadbeefdeadbeef",
        observed_at=_NOW,
        utilization_percent=utilization,
        unobservable_reason=unobservable,
    )


def _gate(*, floor: int = 20, reading: Any = None) -> Any:
    headroom = importlib.import_module(f"{_PACKAGE}._acp_session_headroom")
    return headroom.SessionHeadroomGate(
        reading=_reading() if reading is None else reading, floor=floor
    )


def _item() -> Any:
    types = importlib.import_module("livespec_orchestrator_beads_fabro.types")
    return types.WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Admission reads session headroom",
        description="## Definition of Done\n\n- The reading is journaled.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at=_NOW,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _verdict(*, gate: Any, exhausted: tuple[str, ...] = (), nodes: tuple[Any, ...] = ()) -> Any:
    verdict = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    return verdict.AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=nodes,
        success_critical=("implement",),
        exhausted=exhausted,
        session_headroom=gate,
    )


def _eligibility_filter(
    *, repo: Path, preflight: Any, journal: Any, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[Any], list[Any]]:
    """Run the admission eligibility ladder over one ready row, hermetically."""
    eligibility = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    return eligibility.filter_eligible_candidates(
        repo=repo, preflight=preflight, candidates=[_item()], journal=journal
    )


def _stub_usage_transport(
    *, monkeypatch: pytest.MonkeyPatch, payload: object, calls: list[str]
) -> None:
    """Replace the usage transport with a local stub that records its token."""
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_session_headroom_io")

    def _fake(*, token: str) -> object:
        calls.append(token)
        return payload

    monkeypatch.setattr(module, "_usage_payload", _fake)


def test_the_usage_read_assesses_the_exact_projected_credential_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reading names a digest of the token the dispatch would project.

    The identity is compared against the module's OWN `credential_identity` of
    the same token rather than against a transcribed digest, so the assertion
    cannot pass on a reading taken against a different credential: a stub that
    read some other token would produce a different identity, and the control
    is that the transport was handed exactly this one.
    """
    modules = _modules()
    headroom = modules["_acp_session_headroom"]
    calls: list[str] = []
    _stub_usage_transport(
        monkeypatch=monkeypatch, payload={"five_hour": {"utilization": 65}}, calls=calls
    )

    reading = modules["_dispatcher_session_headroom_io"].read_claude_session_headroom(
        token=_TOKEN, observed_at=_NOW
    )

    assert calls == [_TOKEN]
    assert reading.credential_identity == headroom.credential_identity(token=_TOKEN)
    assert _TOKEN not in reading.credential_identity
    assert reading.utilization_percent == 65.0
    assert reading.remaining_headroom_percent == 35.0
    assert reading.unobservable_reason is None
    assert reading.observed_at == _NOW


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        pytest.param({"five_hour": {}}, "missing", id="missing-figure"),
        pytest.param({"five_hour": {"utilization": "most"}}, "malformed", id="malformed-figure"),
        pytest.param({"five_hour": {"utilization": 140}}, "out-of-range", id="out-of-range"),
        pytest.param(None, "transport-failed", id="transport-failed"),
    ],
)
def test_an_unobservable_reading_is_never_coerced_to_a_number(
    monkeypatch: pytest.MonkeyPatch, payload: object, reason: str
) -> None:
    """Each unobservable result keeps its own token and carries NO utilization.

    The second assertion is the load-bearing one. A zero would read as FULL
    headroom and admit the run the filter exists to hold, and it is exactly what
    a naive `int(value or 0)` produces for every row in this table.
    """
    modules = _modules()
    _stub_usage_transport(monkeypatch=monkeypatch, payload=payload, calls=[])

    reading = modules["_dispatcher_session_headroom_io"].read_claude_session_headroom(
        token=_TOKEN, observed_at=_NOW
    )

    assert reading.unobservable_reason == reason
    assert reading.utilization_percent is None
    assert reading.remaining_headroom_percent is None
    assert reading.observable is False


def test_the_admission_journal_carries_the_reading_for_each_affected_work_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before claim, one record per assessed credential, naming the work-item."""
    modules = _modules()
    records = modules["_dispatcher_session_headroom_records"]
    journal = _MemoryJournal()
    gate = _gate(floor=20)

    admittable, refused = _eligibility_filter(
        repo=tmp_path, preflight=_verdict(gate=gate), journal=journal, monkeypatch=monkeypatch
    )

    assert refused == []
    assert [item.id for item in admittable] == [_ITEM_ID]
    reading_records = [
        record
        for record in journal.records
        if record["stage"] == records.SESSION_HEADROOM_READING_STAGE
    ]
    assert len(reading_records) == 1
    assert reading_records[0]["work_item_id"] == _ITEM_ID
    assert reading_records[0]["credential_identity"] == gate.reading.credential_identity
    assert reading_records[0]["utilization_percent"] == 40.0
    assert reading_records[0]["remaining_headroom_percent"] == 60.0
    assert reading_records[0]["unobservable"] is None
    assert reading_records[0]["observed_at"] == _NOW
    assert reading_records[0]["session_headroom_floor_percent"] == 20
    # The clause forbids a credential value or a raw provider response in the
    # journal, so the whole serialized line is searched rather than one field.
    assert _TOKEN not in json.dumps(reading_records[0], sort_keys=True)


def test_a_zero_floor_still_reads_and_journals_while_skipping_no_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Floor `0` disables BOTH skips and retains the bounded reading attempt.

    The unobservable reading is the discriminating input: under a positive floor
    it skips, so an implementation that short-circuited the read at floor `0`
    would be indistinguishable from this one by skip behaviour alone. The
    journal line is what tells them apart.
    """
    modules = _modules()
    records = modules["_dispatcher_session_headroom_records"]
    unobservable = _reading(utilization=None, unobservable="transport-failed")
    disabled = _gate(floor=0, reading=unobservable)
    journal = _MemoryJournal()

    assert disabled.skips_covered_candidates is False
    assert _gate(floor=20, reading=unobservable).skips_covered_candidates is True

    admittable, refused = _eligibility_filter(
        repo=tmp_path, preflight=_verdict(gate=disabled), journal=journal, monkeypatch=monkeypatch
    )

    assert refused == []
    assert [item.id for item in admittable] == [_ITEM_ID]
    journaled = [
        record
        for record in journal.records
        if record["stage"] == records.SESSION_HEADROOM_READING_STAGE
    ]
    assert len(journaled) == 1
    assert journaled[0]["unobservable"] == "transport-failed"
    assert journaled[0]["utilization_percent"] is None
    assert journaled[0]["session_headroom_floor_percent"] == 0


def test_a_reading_creates_no_observed_availability_record_and_retires_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reading is not availability evidence, in either direction.

    A live domain hold is seeded FIRST so the control can fail in the expensive
    direction: an implementation that treated an above-floor reading as evidence
    would retire it, and that retirement is invisible to every other assertion
    here.
    """
    modules = _modules()
    hold_ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    journal_path = tmp_path / "journal.jsonl"
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    journal = io_module.JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "acp-availability-observed",
            "schema_version": 1,
            "observation_id": "obs-headroom",
            "scope": "availability-domain",
            "hold_key": "anthropic",
            "cause": "quota",
            "occurred_at": _NOW,
            "expires_at": "2099-01-01T00:00:00Z",
        }
    )
    before = hold_ledger.read_acp_hold_ledger(journal_path=journal_path, now_iso=_NOW)

    _ = _eligibility_filter(
        repo=tmp_path,
        preflight=_verdict(gate=_gate(floor=20)),
        journal=journal,
        monkeypatch=monkeypatch,
    )

    after = hold_ledger.read_acp_hold_ledger(journal_path=journal_path, now_iso=_NOW)
    assert [hold.observation_id for hold in after.holds] == [
        hold.observation_id for hold in before.holds
    ]
    assert after.holds
    written = [
        json.loads(line)["stage"] for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert "acp-availability-observed" in written
    assert written.count("acp-availability-observed") == 1
    assert modules["_dispatcher_session_headroom_records"].SESSION_HEADROOM_READING_STAGE in written

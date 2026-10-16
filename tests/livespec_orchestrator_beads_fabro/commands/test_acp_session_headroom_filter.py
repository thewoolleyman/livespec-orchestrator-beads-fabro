"""The headroom SKIP: who leaves the selectable set, and what it records.

Binds the skip half of the "Admission filters candidates by projected Claude
session headroom" paragraph of `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance", the headroom clause added to
section "Factory-configurable ACP fallback priority"'s Per-node selection
eligibility predicate, and the three `SPECIFICATION/scenarios.md` Scenario 60
cases that govern a skip: "Equality passes the headroom filter without
overriding another gate", "A passing usage reading cannot clear observed
availability evidence", and the fallback-selection case.

FOUR CONTROLS CARRY THE WEIGHT, each the mirror image of a plausible mistake:

- EQUALITY PASSES. The clause says so in as many words, and a `<=` comparison
  satisfies every below-floor case in this file while refusing a candidate
  with exactly the headroom its operator declared sufficient.
- AN UNCOVERED CANDIDATE IS NEVER ASSESSED. Asserted by COUNTING the readings,
  because an implementation that assessed everything and skipped only covered
  candidates returns the identical selectable set -- while spending a provider
  request per dispatch on a chain holding no Claude candidate at all.
- A HEADROOM SKIP IS NOT A HOLD. The clause: "it MUST NOT represent that skip
  as an observed hold." So the skip record's typed availability fields stay
  empty, and the reading creates no availability record and retires none --
  the retirement direction asserted against a PRE-SEEDED live hold, because
  "no hold was created" is also true of an implementation that destroyed one.
- THE FILTER RUNS LAST, AFTER THE THREE EXISTING ONES. A durable hold's typed
  cause must survive, and "a successful credential-usability probe MUST NOT
  override a headroom skip" must hold in the other direction too.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CLAUDE_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_SCHEMA_VERSION,
    HOLD_STAGE,
    AcpAvailabilityHold,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-14T12:00:00Z"
_LATER = "2099-01-01T00:00:00Z"
_FLOOR = 20
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    start -> implement
    implement -> exit
"""


def _identity(*, availability_key: str, candidate_key: str) -> AcpCandidateIdentity:
    return AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _covered_builtin() -> AcpCandidate:
    """A candidate the built-in Claude table matched: covered by provenance."""
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=_identity(availability_key=_CLAUDE_PAIR[0], candidate_key=_CLAUDE_PAIR[1]),
    )


def _covered_structured() -> AcpCandidate:
    """A structured candidate that resolved through the `claude-acp` agent entry."""
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-code-acp", env={}, args=()),
        identity=_identity(availability_key="an-opaque-account", candidate_key="opus"),
        agent_id=CLAUDE_AGENT_ID,
    )


def _uncovered(*, candidate_key: str = "gpt-5-5") -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="codex-adapter", env={}, args=()),
        identity=_identity(availability_key="codex", candidate_key=candidate_key),
    )


def _chain(*, candidates: tuple[AcpCandidate, ...], node: str = "implement") -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _policy(
    *,
    utilization: object = 90,
    floor_percent: int = _FLOOR,
    reads: list[str] | None = None,
) -> headroom.SessionHeadroomPolicy:
    """A policy whose reading is fixed, and which records each read it serves."""
    taken: list[headroom.SessionHeadroomReading] = []
    record = [] if reads is None else reads

    def read_once() -> headroom.SessionHeadroomReading:
        if not taken:
            record.append("read")
            taken.append(
                headroom.session_headroom_reading(
                    credential_identity="cred-1", observed_at=_NOW, utilization=utilization
                )
            )
        return taken[0]

    return headroom.SessionHeadroomPolicy(
        floor_percent=floor_percent,
        horizon_minutes=headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        read=read_once,
    )


def _unobservable_policy(*, floor_percent: int = _FLOOR) -> headroom.SessionHeadroomPolicy:
    reading = headroom.unobservable_session_headroom(
        credential_identity="cred-1", observed_at=_NOW, reason="timed-out"
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=floor_percent,
        horizon_minutes=headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        read=lambda: reading,
    )


def _filter(
    *,
    candidates: tuple[AcpCandidate, ...],
    policy: headroom.SessionHeadroomPolicy | None,
    holds: tuple[AcpAvailabilityHold, ...] = (),
    probe: Callable[[str], str] | None = None,
) -> preflight.NodePreflight:
    return preflight.filter_node_candidates(
        chain=_chain(candidates=candidates),
        inputs=preflight.PreflightInputs(
            holds=holds,
            builtin_pairs=_BUILTIN_PAIRS,
            probe=probe,
            headroom=policy,
        ),
        assessed={},
    )


def _keys(*, node: preflight.NodePreflight) -> list[str | None]:
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in node.candidates
    ]


def _hold(*, hold_key: str) -> AcpAvailabilityHold:
    return AcpAvailabilityHold(
        schema_version=HOLD_SCHEMA_VERSION,
        observation_id="acpobs-seeded",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at=_LATER,
    )


def _hold_record(*, hold_key: str) -> dict[str, object]:
    return {
        "stage": HOLD_STAGE,
        "schema_version": HOLD_SCHEMA_VERSION,
        "observation_id": "acpobs-seeded",
        "scope": "availability-domain",
        "hold_key": hold_key,
        "candidate_key": None,
        "cause": "quota",
        "occurred_at": _NOW,
        "expires_at": _LATER,
    }


def _item(**overrides: object) -> WorkItem:
    fields: dict[str, object] = {
        "id": "bd-ib-item",
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    fields.update(overrides)
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _journal_records(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# The skip, and the continuation past it.
# ---------------------------------------------------------------------------


def test_a_below_floor_covered_primary_is_skipped_and_selection_continues() -> None:
    """The next eligible candidate in CONFIGURED order takes the node."""
    node = _filter(
        candidates=(_covered_builtin(), _uncovered(candidate_key="first-fallback")),
        policy=_policy(utilization=90),
    )

    assert _keys(node=node) == ["first-fallback"]
    assert node.exhausted is False
    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.candidate_key == _CLAUDE_PAIR[1]


def test_an_unobservable_reading_skips_a_covered_candidate_under_a_positive_floor() -> None:
    node = _filter(
        candidates=(_covered_builtin(), _uncovered(candidate_key="fallback")),
        policy=_unobservable_policy(),
    )

    assert _keys(node=node) == ["fallback"]
    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom is not None
    assert skip.headroom.unobservable == "timed-out"


def test_remaining_headroom_equal_to_the_floor_passes_the_filter() -> None:
    """Equality PASSES -- the one boundary a `<=` comparison gets wrong."""
    node = _filter(candidates=(_covered_builtin(),), policy=_policy(utilization=80))

    assert _keys(node=node) == [_CLAUDE_PAIR[1]]
    assert node.skipped == ()
    assert node.assessments[0].remaining_percent == 20.0


def test_remaining_headroom_above_the_floor_passes_the_filter() -> None:
    node = _filter(candidates=(_covered_builtin(),), policy=_policy(utilization=10))

    assert _keys(node=node) == [_CLAUDE_PAIR[1]]
    assert node.skipped == ()


def test_a_structured_claude_acp_candidate_is_assessed_by_resolved_agent_id() -> None:
    """Coverage by provenance, on a candidate no built-in table could match."""
    node = _filter(candidates=(_covered_structured(),), policy=_policy(utilization=90))

    assert node.exhausted is True
    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.availability_key == "an-opaque-account"


def test_an_uncovered_chain_is_never_assessed_at_all() -> None:
    """Counted rather than inferred: an over-eager reader returns the same set."""
    reads: list[str] = []
    node = _filter(
        candidates=(_uncovered(), _uncovered(candidate_key="o4-mini")),
        policy=_policy(utilization=99, reads=reads),
    )

    assert reads == []
    assert node.assessments == ()
    assert _keys(node=node) == ["gpt-5-5", "o4-mini"]


def test_two_covered_candidates_share_one_reading() -> None:
    """ "One assessment per distinct projected credential per admission evaluation"."""
    reads: list[str] = []
    node = _filter(
        candidates=(_covered_builtin(), _covered_structured()),
        policy=_policy(utilization=90, reads=reads),
    )

    assert reads == ["read"]
    assert node.exhausted is True
    assert [skip.reason for skip in node.skipped] == [
        preflight.HEADROOM_SKIP,
        preflight.HEADROOM_SKIP,
    ]


def test_no_policy_leaves_the_filter_a_total_no_op() -> None:
    """The additive guarantee: an unwired caller assesses nothing and skips nothing."""
    node = _filter(candidates=(_covered_builtin(),), policy=None)

    assert _keys(node=node) == [_CLAUDE_PAIR[1]]
    assert (node.skipped, node.assessments) == ((), ())


# ---------------------------------------------------------------------------
# A headroom skip is not a hold, and the three earlier filters still win.
# ---------------------------------------------------------------------------


def test_the_skip_record_carries_the_reading_and_the_floor_but_no_hold_identity() -> None:
    node = _filter(candidates=(_covered_builtin(),), policy=_policy(utilization=95))

    [skip] = node.skipped
    assert skip.headroom is not None
    assert skip.headroom.remaining_percent == 5.0
    assert skip.headroom_floor_percent == _FLOOR
    assert (skip.cause, skip.scope, skip.hold_key, skip.condition) == (None, None, None, None)


def test_a_live_hold_still_attributes_its_own_candidate_and_spends_no_reading() -> None:
    """A durable record's typed cause survives, and costs no provider request."""
    reads: list[str] = []
    node = _filter(
        candidates=(_covered_builtin(),),
        policy=_policy(utilization=10, reads=reads),
        holds=(_hold(hold_key=ANTHROPIC_DOMAIN),),
    )

    [skip] = node.skipped
    assert skip.reason == preflight.TYPED_HOLD_SKIP
    assert skip.cause == "quota"
    assert reads == []


def test_a_usable_credential_probe_does_not_override_a_headroom_skip() -> None:
    node = _filter(
        candidates=(_covered_builtin(),),
        policy=_policy(utilization=90),
        probe=lambda _key: "usable",
    )

    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP


def test_a_provider_limited_probe_keeps_its_own_attribution() -> None:
    reads: list[str] = []
    node = _filter(
        candidates=(_covered_builtin(),),
        policy=_policy(utilization=10, reads=reads),
        probe=lambda _key: "rate_limited",
    )

    [skip] = node.skipped
    assert skip.reason == preflight.PROBE_SKIP
    assert skip.condition == "rate_limited"
    assert reads == []


# ---------------------------------------------------------------------------
# The verdict, and the per-work-item journal record.
# ---------------------------------------------------------------------------


def test_the_verdict_carries_the_floor_and_the_deduplicated_readings() -> None:
    verdict = build_acp_preflight_verdict(
        chains={"implement": _chain(candidates=(_covered_builtin(), _covered_structured()))},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_policy(utilization=90)
        ),
    )

    assert verdict.session_headroom_floor_percent == _FLOOR
    assert [reading.credential_identity for reading in verdict.headroom_assessments] == ["cred-1"]
    assert verdict.exhausted == ("implement",)


def test_a_verdict_resolved_without_a_policy_carries_no_floor() -> None:
    """Wait attention and idle-factory consume this verdict and make no request."""
    verdict = build_acp_preflight_verdict(
        chains={"implement": _chain(candidates=(_covered_builtin(),))},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(builtin_pairs=_BUILTIN_PAIRS),
    )

    assert verdict.session_headroom_floor_percent is None
    assert verdict.headroom_assessments == ()
    assert verdict.viable is True


def test_an_admission_pass_journals_one_assessment_record_per_work_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reading reaches the journal through the production admission pass."""
    journal_path = tmp_path / "journal.jsonl"
    verdict = build_acp_preflight_verdict(
        chains={"implement": _chain(candidates=(_covered_builtin(), _uncovered()))},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_policy(utilization=90)
        ),
    )
    _stub_admission(monkeypatch=monkeypatch, tmp_path=tmp_path, verdict=verdict)

    result = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready")],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    assert [item.id for item in result.admitted] == ["bd-ib-ready"]
    [record] = [
        entry
        for entry in _journal_records(path=journal_path)
        if entry.get("stage") == SESSION_HEADROOM_STAGE
    ]
    assert record["work_item_id"] == "bd-ib-ready"
    assert record["session_headroom_floor_percent"] == _FLOOR
    assert record["assessments"] == [
        {
            "credential_identity": "cred-1",
            "utilization_percent": 90.0,
            "remaining_percent": 10.0,
            "unobservable": None,
            "observed_at": _NOW,
            "five_hour_drain_percent_per_hour": None,
        }
    ]


def test_a_reading_creates_no_availability_record_and_retires_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both directions, because "no hold was created" is also true of a wipe.

    The seeded hold covers a domain this chain does not render, so it refuses
    nothing here; what matters is that it is still LIVE after a pass whose
    reading was taken, which is the clause's "A reading creates NO observed
    availability record and retires none."
    """
    journal_path = tmp_path / "journal.jsonl"
    _ = journal_path.write_text(
        json.dumps(_hold_record(hold_key="some-other-domain"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verdict = build_acp_preflight_verdict(
        chains={"implement": _chain(candidates=(_covered_builtin(), _uncovered()))},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=journal_path, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_policy(utilization=90)
        ),
    )
    _stub_admission(monkeypatch=monkeypatch, tmp_path=tmp_path, verdict=verdict)

    _ = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready")],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    records = _journal_records(path=journal_path)
    assert [entry for entry in records if entry.get("stage") == HOLD_STAGE] == [
        _hold_record(hold_key="some-other-domain")
    ]
    ledger = read_acp_hold_ledger(journal_path=journal_path, now_iso=_NOW)
    assert [hold.hold_key for hold in ledger.holds] == ["some-other-domain"]


def test_admission_supplies_a_policy_resolved_from_the_target_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring, asserted on the kwargs the production pass actually passes.

    A policy the preflight is never GIVEN leaves every assertion above true in
    the test suite and the whole clause unreachable in production.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        '{"session_headroom_floor_percent": 45}}}',
        encoding="utf-8",
    )
    resolved: list[dict[str, object]] = []

    def recording_resolve(**kwargs: object) -> AcpPreflightVerdict:
        resolved.append(kwargs)
        return AcpPreflightVerdict(fallback_enabled=False)

    monkeypatch.setattr(admission_module, "resolve_acp_preflight", recording_resolve)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())

    _ = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready")],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        enforce_cap=False,
    )

    [kwargs] = resolved
    policy = kwargs["headroom"]
    assert isinstance(policy, headroom.SessionHeadroomPolicy)
    assert policy.floor_percent == 45
    assert policy.read is not headroom_gate.read_projected_session_headroom


def _stub_admission(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, verdict: AcpPreflightVerdict
) -> None:
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())

"""The three headroom records: the reading, the selection, the refusal.

Binds the headroom arms of "No silent containment" and of "Per-node selection"
in `SPECIFICATION/contracts.md`, and the Scenario 60 arm "Low or unobservable
session headroom with no eligible candidate waits without a claim".

THE CONTROLS THAT CARRY THE WEIGHT:

- The refusal fires ONLY when a headroom skip is what emptied the node. The
  hold-emptied case is the one that can fail for a refusal keyed on
  non-viability alone, and it would report a vendor outage as a usage reading —
  with no hold identity or expiry, which is the field set the generic refusal
  owes and this one must not invent.
- The SELECTION record is withheld for an EMPTY chain. An empty chain selected
  nothing, so a record naming `candidates[0]` there would either crash or name a
  candidate that will not run.
- The item is left ALONE. The refusal is a value plus a journal line; it takes
  no claim, writes no `blocked_reason`, and mints no availability record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_records as records,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    LEGACY_HOLD_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomGate,
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-headroom-records"
_NOW = "2026-10-14T12:00:00Z"


@dataclass(kw_only=True)
class _MemoryJournal:
    appended: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.appended.append(record)


def _gate(*, floor: int = 20, utilization: float | None = 95.0) -> SessionHeadroomGate:
    return SessionHeadroomGate(
        reading=SessionHeadroomReading(
            credential_identity="claude-oauth-bbbbbbbbbbbbbbbb",
            observed_at=_NOW,
            utilization_percent=utilization,
            unobservable_reason=None if utilization is not None else "transport-failed",
        ),
        floor=floor,
    )


def _candidate(*, candidate_key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=candidate_key,
            candidate_key=candidate_key,
            availability_key="anthropic",
        ),
        agent_id="claude-acp",
    )


def _skip(*, candidate_key: str, reason: str = HEADROOM_SKIP) -> SkippedCandidate:
    return SkippedCandidate(
        availability_key="anthropic", candidate_key=candidate_key, reason=reason
    )


def _node(
    *,
    candidates: tuple[AcpCandidate, ...] = (),
    skipped: tuple[SkippedCandidate, ...] = (),
) -> NodePreflight:
    return NodePreflight(node="implement", enabled=True, candidates=candidates, skipped=skipped)


def _verdict(*, nodes: tuple[NodePreflight, ...], exhausted: tuple[str, ...], gate: Any) -> Any:
    return AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=nodes,
        success_critical=("implement",),
        exhausted=exhausted,
        session_headroom=gate,
    )


def _stage(*, journal: _MemoryJournal, stage: str) -> list[dict[str, object]]:
    return [record for record in journal.appended if record["stage"] == stage]


def test_a_selection_record_names_the_skipped_candidate_and_the_governing_floor() -> None:
    """The record identifies the skip and references the assessment and floor."""
    journal = _MemoryJournal()
    gate = _gate()
    node = _node(
        candidates=(_candidate(candidate_key="codex-gpt"),),
        skipped=(_skip(candidate_key="claude-opus"),),
    )

    records.append_session_headroom_records(
        work_item_id=_ITEM,
        verdict=_verdict(nodes=(node,), exhausted=(), gate=gate),
        journal=journal,
    )

    selections = _stage(journal=journal, stage=records.SESSION_HEADROOM_SELECTION_STAGE)
    assert len(selections) == 1
    assert selections[0]["node"] == "implement"
    assert selections[0]["selected_candidate_key"] == "codex-gpt"
    assert selections[0]["skipped_candidates"] == [
        {"availability_key": "anthropic", "candidate_key": "claude-opus", "reason": HEADROOM_SKIP}
    ]
    assert selections[0]["session_headroom_floor_percent"] == 20
    assert selections[0]["credential_identity"] == gate.reading.credential_identity
    assert selections[0]["remaining_headroom_percent"] == 5.0
    assert selections[0]["observed_at"] == _NOW
    # No hold identity, cause or expiry is invented for a reading that minted
    # no hold -- the clause forbids representing the skip as an observed hold.
    assert "hold_key" not in selections[0]
    assert "expires_at" not in selections[0]


@pytest.mark.parametrize(
    ("candidates", "skipped", "expected"),
    [
        pytest.param(
            (), (_skip(candidate_key="claude-opus"),), 0, id="empty-chain-selects-nothing"
        ),
        pytest.param(
            (_candidate(candidate_key="claude-opus"),), (), 0, id="nothing-headroom-skipped"
        ),
        pytest.param(
            (_candidate(candidate_key="codex-gpt"),),
            (_skip(candidate_key="claude-opus", reason=LEGACY_HOLD_SKIP),),
            0,
            id="skipped-by-a-hold-not-by-headroom",
        ),
    ],
)
def test_no_selection_record_is_written_without_a_headroom_skip_and_a_selection(
    candidates: tuple[AcpCandidate, ...], skipped: tuple[SkippedCandidate, ...], expected: int
) -> None:
    """Both conditions are required, and each is a different wrong record.

    An empty chain selected nothing; a node nothing was headroom-skipped on owes
    no reference to an assessment; and a hold-skipped candidate belongs to the
    hold's own records, not to this one.
    """
    journal = _MemoryJournal()

    records.append_session_headroom_records(
        work_item_id=_ITEM,
        verdict=_verdict(
            nodes=(_node(candidates=candidates, skipped=skipped),), exhausted=(), gate=_gate()
        ),
        journal=journal,
    )

    assert len(_stage(journal=journal, stage=records.SESSION_HEADROOM_SELECTION_STAGE)) == expected
    # The READING record is written on every one of these, which is what makes
    # a floor of 0 and a no-skip pass observable at all.
    assert len(_stage(journal=journal, stage=records.SESSION_HEADROOM_READING_STAGE)) == 1


def test_a_verdict_with_no_reading_journals_nothing() -> None:
    """The additive guarantee: no gate, no line."""
    journal = _MemoryJournal()

    records.append_session_headroom_records(
        work_item_id=_ITEM, verdict=_verdict(nodes=(), exhausted=(), gate=None), journal=journal
    )

    assert journal.appended == []


def test_the_containment_refusal_names_the_assessment_node_and_reevaluation(
    tmp_path: Path,
) -> None:
    """Every field the clause requires of a headroom-governed refusal."""
    journal = _MemoryJournal()
    node = _node(
        candidates=(),
        skipped=(_skip(candidate_key="claude-opus"), _skip(candidate_key="claude-sonnet")),
    )

    outcome = records.session_headroom_refusal(
        repo=tmp_path,
        work_item_id=_ITEM,
        verdict=_verdict(nodes=(node,), exhausted=("implement",), gate=_gate(utilization=None)),
        journal=journal,
        now_iso=_NOW,
    )

    assert outcome is not None
    assert outcome.stage == records.SESSION_HEADROOM_REFUSAL_STAGE
    assert outcome.work_item_id == _ITEM
    assert "unobservable" in outcome.detail
    refusals = _stage(journal=journal, stage=records.SESSION_HEADROOM_REFUSAL_STAGE)
    assert len(refusals) == 1
    assert refusals[0]["governing_condition"] == "admission_session_headroom"
    assert refusals[0]["admission_required_node"] == "implement"
    # The default re-probe cadence is 300 seconds, so the instant is five
    # minutes on from the pass's own `now`.
    assert refusals[0]["scheduled_reevaluation_at"] == "2026-10-14T12:05:00Z"
    assert refusals[0]["credential_identity"] == "claude-oauth-bbbbbbbbbbbbbbbb"
    assert refusals[0]["unobservable"] == "transport-failed"
    assert refusals[0]["utilization_percent"] is None
    assert refusals[0]["observed_at"] == _NOW
    assert refusals[0]["session_headroom_floor_percent"] == 20
    assert [entry["candidate_key"] for entry in refusals[0]["skipped_candidates"]] == [  # pyright: ignore[reportIndexIssue, reportArgumentType, reportGeneralTypeIssues, reportUnknownVariableType]
        "claude-opus",
        "claude-sonnet",
    ]


def test_an_observable_reading_refusal_reports_the_remaining_percentage(
    tmp_path: Path,
) -> None:
    """The below-floor arm reports the figure rather than an unobservable token."""
    journal = _MemoryJournal()
    node = _node(candidates=(), skipped=(_skip(candidate_key="claude-opus"),))

    outcome = records.session_headroom_refusal(
        repo=tmp_path,
        work_item_id=_ITEM,
        verdict=_verdict(nodes=(node,), exhausted=("implement",), gate=_gate(utilization=95.0)),
        journal=journal,
        now_iso=_NOW,
    )

    assert outcome is not None
    assert "5% remaining" in outcome.detail


@pytest.mark.parametrize(
    ("nodes", "exhausted", "gate"),
    [
        pytest.param((), (), _gate(), id="viable-verdict"),
        pytest.param((), (), None, id="no-reading-taken"),
        pytest.param(
            (_node(candidates=(), skipped=(_skip(candidate_key="x", reason=LEGACY_HOLD_SKIP),)),),
            ("implement",),
            _gate(),
            id="emptied-by-a-hold",
        ),
        pytest.param(
            (_node(candidates=(), skipped=(_skip(candidate_key="x"),)),),
            ("review",),
            _gate(),
            id="exhausted-node-not-filtered",
        ),
    ],
)
def test_the_refusal_is_withheld_unless_headroom_emptied_an_exhausted_node(
    tmp_path: Path, nodes: tuple[NodePreflight, ...], exhausted: tuple[str, ...], gate: Any
) -> None:
    """The hold-emptied case is the expensive one to get wrong.

    A refusal keyed on non-viability alone would attribute a vendor outage to a
    usage reading, and would do it with no hold identity or expiry -- so the
    operator would be told to wait on a reading while a hold they could clear
    was what actually refused the item.
    """
    journal = _MemoryJournal()

    outcome = records.session_headroom_refusal(
        repo=tmp_path,
        work_item_id=_ITEM,
        verdict=_verdict(nodes=nodes, exhausted=exhausted, gate=gate),
        journal=journal,
        now_iso=_NOW,
    )

    assert outcome is None
    assert _stage(journal=journal, stage=records.SESSION_HEADROOM_REFUSAL_STAGE) == []


def test_the_admission_ladder_refuses_without_touching_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A headroom wait leaves the row `ready`, unclaimed and unblocked.

    This is the eligibility-ladder integration of the refusal above, and the
    store read-back is the load-bearing half: a refusal that parked the item
    would satisfy every assertion about the journal while converting an
    automatic wait into one a human has to release.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )
    item = WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="Waits on session headroom",
        description="## Definition of Done\n\n- The item stays ready.\n",
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
    append_work_item(path=config, item=item)
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    journal = JournalFile(path=repo / "journal.jsonl")
    node = _node(candidates=(), skipped=(_skip(candidate_key="claude-opus"),))

    admittable, refused = eligibility.filter_eligible_candidates(
        repo=repo,
        preflight=_verdict(nodes=(node,), exhausted=("implement",), gate=_gate()),
        candidates=[item],
        journal=journal,
    )

    assert admittable == []
    assert [outcome.stage for outcome in refused] == [records.SESSION_HEADROOM_REFUSAL_STAGE]
    stored = materialize_work_items(records=read_work_items(path=config))[_ITEM]
    assert stored.status == "ready"
    assert stored.assignee is None
    assert stored.blocked_reason is None
    written = [
        json.loads(line)["stage"]
        for line in (repo / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    # The reading is journaled before the refusal, and NO availability record
    # is minted: a reading is not availability evidence in either direction.
    assert written == [
        records.SESSION_HEADROOM_READING_STAGE,
        records.SESSION_HEADROOM_REFUSAL_STAGE,
    ]

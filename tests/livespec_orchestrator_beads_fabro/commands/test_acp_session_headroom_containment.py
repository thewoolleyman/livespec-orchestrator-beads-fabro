"""The containment refusal a headroom-emptied node produces, and what it costs.

Binds `SPECIFICATION/scenarios.md` Scenario 60's "Low or unobservable session
headroom with no eligible candidate waits without a claim" and the headroom
sentence added to the "No silent containment" containment-refusal bullet of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "A headroom-governed refusal MUST additionally name the
assessed credential identity, reading or explicit unobservable result,
observation time, governing floor, and skipped candidates for the
admission-required node lacking an eligible candidate."

THE EXPENSIVE HALF IS THE ABSENCE OF A WRITE, so it is asserted by RECORDING
every ledger write the pass attempts and finding none. A refusal that also
claimed the item, or marked it blocked, leaves work stranded `active` with no
run behind it -- the shape this clause exists to prevent -- and nothing in the
refusal record itself would say so.

THE NEGATIVE CONTROL IS WHAT GIVES THE POSITIVE ONE MEANING. A refusal governed
by a typed availability HOLD must carry no headroom key at all: without that
case, an implementation that stamped the headroom block onto every refusal
would satisfy every other assertion here while telling an operator a credential
was assessed when none was.
"""

from __future__ import annotations

import json
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
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import (
    HOLD_SCHEMA_VERSION,
    AcpAvailabilityHold,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-14T12:00:00Z"
_LATER = "2099-01-01T00:00:00Z"
_FLOOR = 20
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_SECOND_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-fedcba9876543210")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR, _SECOND_PAIR})

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


def _covered(*, pair: tuple[str, str]) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=_identity(availability_key=pair[0], candidate_key=pair[1]),
    )


def _chain(*, candidates: tuple[AcpCandidate, ...]) -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node="implement",
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _reading(*, utilization: object) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=utilization
    )


def _policy(*, reading: headroom.SessionHeadroomReading) -> headroom.SessionHeadroomPolicy:
    return headroom.SessionHeadroomPolicy(floor_percent=_FLOOR, read=lambda: reading)


def _verdict(
    *,
    reading: headroom.SessionHeadroomReading | None = None,
    holds: tuple[AcpAvailabilityHold, ...] = (),
) -> AcpPreflightVerdict:
    return build_acp_preflight_verdict(
        chains={
            "implement": _chain(
                candidates=(_covered(pair=_CLAUDE_PAIR), _covered(pair=_SECOND_PAIR))
            )
        },
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            holds=holds,
            builtin_pairs=_BUILTIN_PAIRS,
            headroom=None if reading is None else _policy(reading=reading),
        ),
    )


def _hold() -> AcpAvailabilityHold:
    return AcpAvailabilityHold(
        schema_version=HOLD_SCHEMA_VERSION,
        observation_id="acpobs-seeded",
        scope="availability-domain",
        hold_key=ANTHROPIC_DOMAIN,
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at=_LATER,
    )


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


def _run_admission(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: AcpPreflightVerdict
) -> tuple[admission_module.Admission, list[dict[str, Any]], list[dict[str, object]]]:
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission_module,
        "update_work_item_status",
        lambda **kwargs: writes.append(dict(kwargs)),
    )
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal_path = tmp_path / "journal.jsonl"

    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready")],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return admission, records, writes


def _refusal(*, records: list[dict[str, Any]]) -> dict[str, Any]:
    [record] = [record for record in records if record["stage"] == ACP_PREFLIGHT_REFUSAL_STAGE]
    return record


@pytest.mark.parametrize(
    ("utilization", "expected"),
    [
        (
            95,
            {
                "credential_identity": "cred-1",
                "utilization_percent": 95.0,
                "remaining_percent": 5.0,
                "unobservable": None,
                "observed_at": _NOW,
                "seven_day_utilization_percent": None,
            },
        ),
        (
            "not-a-number",
            {
                "credential_identity": "cred-1",
                "utilization_percent": None,
                "remaining_percent": None,
                "unobservable": headroom.UNREADABLE_UTILIZATION,
                "observed_at": _NOW,
                "seven_day_utilization_percent": None,
            },
        ),
    ],
)
def test_a_headroom_emptied_node_waits_without_a_claim_and_says_what_it_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, utilization: object, expected: dict[str, Any]
) -> None:
    """Both arms of the scenario: a below-floor reading and an unobservable one."""
    admission, records, writes = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(reading=_reading(utilization=utilization)),
    )

    # The item stays ready with no dispatch claim and no blocked_reason: the
    # pass attempted NO ledger write at all.
    assert admission.admitted == []
    assert writes == []
    assert [outcome.work_item_id for outcome in admission.refused] == ["bd-ib-ready"]

    refusal = _refusal(records=records)
    assert refusal["work_item_id"] == "bd-ib-ready"
    assert refusal["exhausted"] == ["implement"]
    assert refusal["session_headroom_floor_percent"] == _FLOOR
    assert refusal["session_headroom_assessments"] == [expected]
    assert refusal["session_headroom_skipped"] == {
        "implement": [
            {
                "availability_key": _CLAUDE_PAIR[0],
                "candidate_key": _CLAUDE_PAIR[1],
                "session_headroom_floor_percent": _FLOOR,
                "headroom": expected,
            },
            {
                "availability_key": _SECOND_PAIR[0],
                "candidate_key": _SECOND_PAIR[1],
                "session_headroom_floor_percent": _FLOOR,
                "headroom": expected,
            },
        ]
    }


def test_a_hold_governed_refusal_carries_no_headroom_key_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control: headroom names nothing it did not measure.

    A live typed hold empties the chain before any reading is taken, so the
    refusal is hold-governed and the clause's additional naming requirement
    does not apply to it. A block stamped on unconditionally would claim a
    credential was assessed when the filter never reached it.
    """
    admission, records, writes = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(reading=_reading(utilization=5), holds=(_hold(),)),
    )

    assert (admission.admitted, writes) == ([], [])
    refusal = _refusal(records=records)
    assert refusal["exhausted"] == ["implement"]
    assert [key for key in refusal if key.startswith("session_headroom")] == []


def test_a_refusal_resolved_without_a_policy_carries_no_headroom_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chain emptied with no policy supplied reports nothing about headroom."""
    _admission, records, _writes = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=AcpPreflightVerdict(
            fallback_enabled=True, success_critical=("implement",), exhausted=("implement",)
        ),
    )

    refusal = _refusal(records=records)
    assert [key for key in refusal if key.startswith("session_headroom")] == []

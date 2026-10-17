"""A floor of ZERO: the reading is still taken and journaled, and skips nothing.

Binds `SPECIFICATION/scenarios.md` Scenario 60's "A disabled floor retains
observation without refusing on unobservability" and the sentence it comes from
in `SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "A floor of 0 disables both kinds of headroom skip while
retaining the bounded reading attempt and journal record; it disables no other
admission condition."

THE UNOBSERVABLE ARM IS THE WHOLE POINT, and it is the only arm that can fail.
A below-floor skip is already impossible at a floor of 0 -- no remaining
headroom is strictly below zero -- so a predicate written without the
disabled-floor guard passes every numeric case here and still skips on every
unobservable reading. That is the measured behaviour this case exists to
retire: an operator who sets the dial to 0 to switch the filter OFF would find
their dispatches refused whenever the usage endpoint timed out.

"RETAINING THE BOUNDED READING ATTEMPT AND JOURNAL RECORD" IS ASSERTED TOO,
because the cheap wrong implementation of a disabled filter is to stop reading.
A floor of 0 is an operator saying "do not act on this", not "do not measure
it": the journal row is what makes the dial's effect reviewable, and it is the
only evidence that the credential was ever looked at.
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
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-14T12:00:00Z"
_DISABLED = 0
_POSITIVE = 20
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    start -> implement
    implement -> exit
"""


def _covered() -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name="built-in Anthropic ACP adapter",
            candidate_key=_CLAUDE_PAIR[1],
            availability_key=_CLAUDE_PAIR[0],
        ),
    )


def _chain() -> ResolvedAcpChain:
    return ResolvedAcpChain(
        node="implement",
        primary=_covered(),
        fallbacks=(),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _unobservable_policy(*, floor_percent: int) -> headroom.SessionHeadroomPolicy:
    reading = headroom.unobservable_session_headroom(
        credential_identity="cred-1", observed_at=_NOW, reason="timed-out"
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=floor_percent,
        horizon_minutes=headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        read=lambda: reading,
    )


def _spent_policy(*, floor_percent: int) -> headroom.SessionHeadroomPolicy:
    """A credential whose five-hour window is entirely spent: 0 percent remaining."""
    reading = headroom.session_headroom_reading(
        credential_identity="cred-1", observed_at=_NOW, utilization=100
    )
    return headroom.SessionHeadroomPolicy(
        floor_percent=floor_percent,
        horizon_minutes=headroom.DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
        read=lambda: reading,
    )


def _verdict(*, policy: headroom.SessionHeadroomPolicy) -> AcpPreflightVerdict:
    return build_acp_preflight_verdict(
        chains={"implement": _chain()},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(builtin_pairs=_BUILTIN_PAIRS, headroom=policy),
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
) -> tuple[list[str], list[dict[str, Any]]]:
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
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
    return [item.id for item in admission.admitted], records


def test_a_disabled_floor_does_not_skip_an_unobservable_reading() -> None:
    """The one arm a floor-blind predicate gets wrong."""
    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_unobservable_policy(floor_percent=_DISABLED)
        ),
        assessed={},
    )

    assert node.skipped == ()
    assert [candidate.identity.candidate_key for candidate in node.candidates] == [  # pyright: ignore[reportOptionalMemberAccess]
        _CLAUDE_PAIR[1]
    ]
    assert [reading.unobservable for reading in node.assessments] == ["timed-out"]


def test_a_positive_floor_still_skips_that_same_unobservable_reading() -> None:
    """The control: the guard is keyed on the floor, not simply deleted."""
    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_unobservable_policy(floor_percent=_POSITIVE)
        ),
        assessed={},
    )

    assert [skip.reason for skip in node.skipped] == [preflight.HEADROOM_SKIP]
    assert node.candidates == ()


def test_a_disabled_floor_does_not_skip_a_wholly_spent_allowance() -> None:
    """Zero percent remaining is not strictly below a floor of zero either."""
    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_spent_policy(floor_percent=_DISABLED)
        ),
        assessed={},
    )

    assert node.skipped == ()
    assert [reading.remaining_percent for reading in node.assessments] == [0.0]


def test_a_disabled_floor_still_journals_the_reading_it_took(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dial switches the FILTER off, never the measurement."""
    admitted, records = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(policy=_unobservable_policy(floor_percent=_DISABLED)),
    )

    assert admitted == ["bd-ib-ready"]
    assert [record for record in records if record["stage"] == ACP_PREFLIGHT_REFUSAL_STAGE] == []
    [record] = [record for record in records if record["stage"] == SESSION_HEADROOM_STAGE]
    assert record["session_headroom_floor_percent"] == _DISABLED
    assert record["assessments"] == [
        {
            "credential_identity": "cred-1",
            "utilization_percent": None,
            "remaining_percent": None,
            "unobservable": "timed-out",
            "observed_at": _NOW,
            "five_hour_drain_percent_per_hour": None,
            "projection": None,
            "unverified_provider_reset_claim": None,
        }
    ]
    assert record["node_selections"]["implement"]["headroom_skipped"] == []
    assert record["node_selections"]["implement"]["selected_candidate_key"] == _CLAUDE_PAIR[1]

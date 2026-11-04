"""A seven-day skip is NAMED a seven-day skip, on both records that report one.

Binds the naming sentence of the seven-day half of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom": "a headroom-governed refusal record and the per-node
selection record MUST name it as a seven-day skip, distinct from a floor skip
and a projection skip". The governing scenario is `SPECIFICATION/scenarios.md`
Scenario 231.

THESE CASES ARE CONTROLS, and that is stated rather than left for a reader to
work out. The kind a skip reports is ONE field the filter sets and all three
record surfaces render, so the moment the filter learned to report a seven-day
skip both records named it -- there is no state of this package in which the
filter reports the kind and a record drops it, so none of these cases could
have failed before that landed. They are here because the consequence is what
the clause actually requires, and because the opposite design -- a second skip
REASON per shortfall -- is the one a later edit is most likely to reach for,
which would leave every consumer keying on the reason unable to see a weekly
skip at all. These assertions are what would fail then.

THE THREE KINDS ARE ASSERTED AS A SET, ON ONE SURFACE, because the requirement
is a DISTINCTION rather than a label: a build stamping one word onto every
headroom skip satisfies any single-kind case perfectly, and its records would
look right. The parametrization therefore drives all three shortfalls through
the same record and asserts the three words differ.

THE REFUSAL CASE DRIVES THE REAL ADMISSION PASS, because the clause's subject
is the record a refused dispatch leaves behind, and a projection asserted in
isolation would pass while nothing wrote it into the journal an operator reads.
Its expensive half is an ABSENCE: a refusal that also claimed the item would
strand work `active` with no run behind it, and the refusal record itself would
not say so.

Everything is HERMETIC: the provider read is the policy's injected seam, the
ledger write is recorded rather than performed, and no credential value leaves
this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_projection as projection_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
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
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-22T12:00:00Z"
_EARLIER = "2026-10-22T11:30:00Z"
_IDENTITY = "cred-naming"
_FLOOR = 20
_HORIZON = 180
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    start -> implement
    implement -> exit
"""


def _chain() -> ResolvedAcpChain:
    covered = AcpCandidate(
        adapter=AcpAdapter(command="claude-adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"{_CLAUDE_PAIR[0]}/{_CLAUDE_PAIR[1]}",
            candidate_key=_CLAUDE_PAIR[1],
            availability_key=_CLAUDE_PAIR[0],
        ),
    )
    return ResolvedAcpChain(
        node="implement",
        primary=covered,
        fallbacks=(),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _weekly_refused() -> headroom.SessionHeadroomReading:
    """Ample five-hour room, no projection, and a refused weekly allowance."""
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization=5,
        seven_day=headroom.seven_day_reading(
            utilization=100.0, status=headroom.SEVEN_DAY_REJECTED_STATUS
        ),
    )


def _floor_short() -> headroom.SessionHeadroomReading:
    """A reading the FLOOR settles, whose weekly window says nothing."""
    reading = headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=95
    )
    return projection_module.reading_with_projection(
        reading=reading,
        projection=projection_module.session_headroom_projection(
            reading=reading, baseline=None, floor_percent=_FLOOR, horizon_minutes=_HORIZON
        ),
    )


def _projected() -> headroom.SessionHeadroomReading:
    """50 points from empty at 25 an hour: two hours, inside a three-hour horizon."""
    reading = headroom.SessionHeadroomReading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization_percent=50.0,
        remaining_percent=50.0,
        five_hour_drain_percent_per_hour=25.0,
    )
    return projection_module.reading_with_projection(
        reading=reading,
        projection=projection_module.session_headroom_projection(
            reading=reading,
            baseline=SessionHeadroomBaseline(
                utilization_percent=10.0, observed_at=_EARLIER, elapsed_hours=0.5
            ),
            floor_percent=_FLOOR,
            horizon_minutes=_HORIZON,
        ),
    )


def _policy(*, reading: headroom.SessionHeadroomReading) -> headroom.SessionHeadroomPolicy:
    return headroom.SessionHeadroomPolicy(
        floor_percent=_FLOOR, horizon_minutes=_HORIZON, read=lambda: reading
    )


def _verdict(*, reading: headroom.SessionHeadroomReading) -> Any:
    return build_acp_preflight_verdict(
        chains={"implement": _chain()},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS, headroom=_policy(reading=reading)
        ),
    )


@pytest.mark.parametrize(
    ("reading", "expected_kind"),
    [
        (_floor_short(), preflight.FLOOR_SKIP_KIND),
        (_weekly_refused(), preflight.SEVEN_DAY_SKIP_KIND),
        (_projected(), preflight.PROJECTION_SKIP_KIND),
    ],
    ids=["floor", "seven-day", "projection"],
)
def test_the_selection_entry_names_each_shortfall_as_its_own_kind(
    reading: headroom.SessionHeadroomReading, expected_kind: str
) -> None:
    """All three kinds through one surface, so the DISTINCTION is what is asserted."""
    verdict = _verdict(reading=reading)

    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item",
        floor_percent=_FLOOR,
        assessments=verdict.headroom_assessments,
        nodes=verdict.nodes,
    )

    selections = cast("dict[str, dict[str, object]]", record["node_selections"])
    [skipped] = cast("list[dict[str, object]]", selections["implement"]["headroom_skipped"])
    assert skipped["headroom_skip_kind"] == expected_kind
    assert skipped["session_headroom_floor_percent"] == _FLOOR
    assert skipped["session_headroom_horizon_minutes"] == _HORIZON
    # All three words differ, so no one of them is a label the build stamps on
    # every headroom skip.
    assert (
        len(
            {
                preflight.FLOOR_SKIP_KIND,
                preflight.SEVEN_DAY_SKIP_KIND,
                preflight.PROJECTION_SKIP_KIND,
            }
        )
        == 3
    )
    # And the weekly figures travel with the skip, so a reader asking why an
    # account lost its week can check the record against the account.
    carried = cast("dict[str, object]", skipped["headroom"])
    weekly = cast("dict[str, object]", carried["seven_day"])
    assert weekly["status"] == (
        headroom.SEVEN_DAY_REJECTED_STATUS
        if expected_kind == preflight.SEVEN_DAY_SKIP_KIND
        else None
    )


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _item() -> WorkItem:
    fields: dict[str, object] = {
        "id": "bd-ib-ready",
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-10-22T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


def test_a_weekly_emptied_node_refuses_naming_the_seven_day_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No claim, no blocked reason, and a refusal record naming the weekly skip."""
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(
        admission_module,
        "resolve_acp_preflight",
        lambda **_: _verdict(reading=_weekly_refused()),
    )
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission_module, "update_work_item_status", lambda **kwargs: writes.append(dict(kwargs))
    )
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal_path = tmp_path / "journal.jsonl"

    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item()],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    assert admission.admitted == []
    assert writes == []
    assert [outcome.work_item_id for outcome in admission.refused] == ["bd-ib-ready"]
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    [refusal] = [record for record in records if record["stage"] == ACP_PREFLIGHT_REFUSAL_STAGE]
    assert refusal["exhausted"] == ["implement"]
    assert refusal["session_headroom_floor_percent"] == _FLOOR
    [skipped] = refusal["session_headroom_skipped"]["implement"]
    assert skipped["headroom_skip_kind"] == preflight.SEVEN_DAY_SKIP_KIND
    assert skipped["headroom"]["seven_day"] == {
        "utilization_percent": 100.0,
        "status": headroom.SEVEN_DAY_REJECTED_STATUS,
        "unobservable": None,
    }
    # The five-hour window was AMPLE, so the refusal is attributable to the
    # weekly reading rather than to the dial that governs the other one.
    assert skipped["headroom"]["remaining_percent"] == 95.0

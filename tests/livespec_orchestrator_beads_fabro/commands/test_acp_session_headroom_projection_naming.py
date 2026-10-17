"""A projection skip is NAMED a projection skip, and nothing overrides it.

Binds the naming and non-override sentences of `SPECIFICATION/contracts.md`
section "Dispatcher admission, WIP cap, and post-merge acceptance", paragraph
"Admission filters candidates by projected Claude session headroom": "A
headroom-governed refusal record and the per-node selection record MUST name a
projection skip as a projection skip, distinct from a floor skip, and MUST
reference the assessment carrying the projection"; "a successful
credential-usability probe MUST NOT override it"; and "an emptied
admission-required node leaves a ready item ready without a claim or blocked
reason". The refusal's own naming obligation is the "No silent containment"
bullet of the same section, which a headroom-governed refusal must additionally
satisfy by naming "governing floor and governing horizon, the projection
result".

THE TWO KINDS ARE ASSERTED AS A PAIR, ON ONE SURFACE, because the requirement
is a DISTINCTION rather than a label. A build that stamped `projection` onto
every headroom skip would satisfy a projection-only case perfectly, and the
record it wrote would look right -- the floor case is the only thing that can
catch it. The same pairing is why both cases assert the governing horizon:
a horizon written only onto the projection kind would leave a reader unable to
tell a floor skip taken under a disabled horizon from one taken under 180.

THE REFERENCE IS THE CREDENTIAL IDENTITY, which is how a reader joins a skip to
the assessment list the same record carries. The projection rides inside that
assessment, so naming the identity is naming "the assessment carrying the
projection"; a skip that embedded its own copy of the figures would be a second
account of one measurement.

THE PROBE NON-OVERRIDE IS ASSERTED WITH A PROBE THAT ANSWERS `usable`, which is
the measured failure this whole clause exists for: on hp 2026-10-14 a run was
refused mid-implement on the session limit while `claude-cred-status` returned
`usable` two minutes later. A filter consulting the probe as evidence of
headroom would admit exactly that dispatch.

THE EXPENSIVE HALF IS THE ABSENCE OF A WRITE, so the end-to-end case records
every ledger write the pass attempts and finds none. A refusal that also claimed
the item, or marked it blocked, strands work `active` with no run behind it --
and nothing in the refusal record itself would say so.
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

_NOW = "2026-10-16T12:00:00Z"
_EARLIER = "2026-10-16T11:30:00Z"
_IDENTITY = "cred-1"
_FLOOR = 20
_HORIZON = 180
_CLAUDE_PAIR = (ANTHROPIC_DOMAIN, "builtin-anthropic-0123456789abcdef")
_BUILTIN_PAIRS = frozenset({_CLAUDE_PAIR})

# Spelled as LITERALS and bound to the exported names by the cases below,
# because this file's Red predates the constants it binds and a Red's test
# bytes are fixed across its Red-to-Green pair.
_FLOOR_KIND = "floor"
_PROJECTION_KIND = "projection"

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
            display_name=f"{_CLAUDE_PAIR[0]}/{_CLAUDE_PAIR[1]}",
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


def _projected_reading() -> headroom.SessionHeadroomReading:
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


def _floor_skipped_reading() -> headroom.SessionHeadroomReading:
    """A reading the FLOOR settled, which is therefore never projected at all."""
    reading = headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=95
    )
    return projection_module.reading_with_projection(
        reading=reading,
        projection=projection_module.session_headroom_projection(
            reading=reading, baseline=None, floor_percent=_FLOOR, horizon_minutes=_HORIZON
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
        (_floor_skipped_reading(), _FLOOR_KIND),
        (_projected_reading(), _PROJECTION_KIND),
    ],
)
def test_the_selection_entry_names_the_skip_kind_the_horizon_and_the_assessment(
    reading: headroom.SessionHeadroomReading, expected_kind: str
) -> None:
    """Both kinds, on one surface, so the DISTINCTION is what is asserted."""
    assert getattr(preflight, "FLOOR_SKIP_KIND", None) == _FLOOR_KIND
    assert getattr(preflight, "PROJECTION_SKIP_KIND", None) == _PROJECTION_KIND
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
    # The reference a reader joins the skip to the assessment list by, and the
    # projection result that list carries for it.
    carried = cast("dict[str, object]", skipped["headroom"])
    assert carried["credential_identity"] == _IDENTITY
    assert cast("dict[str, object]", carried["projection"])["projection_skip_applied"] is (
        expected_kind == _PROJECTION_KIND
    )
    assert _FLOOR_KIND != _PROJECTION_KIND


def test_a_successful_credential_probe_does_not_override_a_projection_skip() -> None:
    """The probe answers `usable` right up to the session limit, measured on hp."""
    probes: list[str] = []

    def _probe(key: str) -> str:
        probes.append(key)
        return "usable"

    node = preflight.filter_node_candidates(
        chain=_chain(),
        inputs=preflight.PreflightInputs(
            builtin_pairs=_BUILTIN_PAIRS,
            probe=_probe,
            headroom=_policy(reading=_projected_reading()),
        ),
        assessed={},
    )

    assert probes == [_CLAUDE_PAIR[0]]
    assert node.candidates == ()
    [skip] = node.skipped
    assert skip.reason == preflight.HEADROOM_SKIP
    assert skip.headroom_skip_kind == _PROJECTION_KIND


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
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


def test_a_projection_emptied_node_leaves_a_ready_item_ready_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No claim, no blocked reason, and a refusal naming the projection skip."""
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(
        admission_module,
        "resolve_acp_preflight",
        lambda **_: _verdict(reading=_projected_reading()),
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
    assert refusal["session_headroom_horizon_minutes"] == _HORIZON
    [skipped] = refusal["session_headroom_skipped"]["implement"]
    assert skipped["headroom_skip_kind"] == _PROJECTION_KIND
    assert skipped["headroom"]["projection"]["result"] == headroom.PROJECTED_RESULT
    assert skipped["headroom"]["projection"]["projected_exhaustion_at"] == "2026-10-16T14:00:00Z"

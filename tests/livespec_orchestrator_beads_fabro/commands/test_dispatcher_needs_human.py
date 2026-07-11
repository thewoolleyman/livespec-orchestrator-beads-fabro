"""Unit coverage for the needs-human resolve-or-escalate seam + classifier (S4).

Covers `livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human`: the
injectable `NeedsHumanResolver` seam (with its scripted `Recording` double), the
`NeedsHumanResolution` verdict, and the pure `resolution_resolves` engine rule
that folds the confidence-bounded and design-bounded escalation sources plus the
deterministic `human-only` guard into one resolve-or-escalate verdict
(`SPECIFICATION/scenarios.md` Scenarios 35 and 36; the truly-unresolvable set in
`SPECIFICATION/spec.md`).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human import (
    NEEDS_HUMAN_GATE,
    NeedsHumanResolution,
    RecordingNeedsHumanResolver,
    resolution_resolves,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-nh1",
        type="task",
        status="active",
        title="A parked task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _blocked(*, item_id: str = "bd-ib-nh1") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run 01RUN parked at the in-loop human gate (needs-human)",
    )


# ---------------------------------------------------------------------------
# NeedsHumanResolution + the recording double
# ---------------------------------------------------------------------------


def test_resolution_carries_its_three_fields() -> None:
    resolution = NeedsHumanResolution(resolvable=True, design_gated=False, decision="did X")
    assert resolution.resolvable is True
    assert resolution.design_gated is False
    assert resolution.decision == "did X"


def test_recording_resolver_returns_scripted_verdict_and_records_the_call() -> None:
    verdict = NeedsHumanResolution(resolvable=True, design_gated=False, decision="resolved")
    resolver = RecordingNeedsHumanResolver(verdict=verdict)

    got = resolver.resolve(item=_item(), outcome=_blocked(), repo=Path("/repo"))

    assert got == verdict
    assert resolver.calls == [
        ("bd-ib-nh1", "run 01RUN parked at the in-loop human gate (needs-human)")
    ]


# ---------------------------------------------------------------------------
# resolution_resolves — the pure engine rule (Scenarios 35, 36)
# ---------------------------------------------------------------------------


def test_resolves_a_confident_non_gated_non_human_only_block() -> None:
    # Scenario 35: a confidently-resolvable decision on a routine item resolves.
    resolution = NeedsHumanResolution(resolvable=True, design_gated=False, decision="resolved")
    assert resolution_resolves(item=_item(), resolution=resolution) is True


def test_escalates_a_low_confidence_block() -> None:
    # Scenario 36 leg 1: the LLM cannot confidently resolve it -> escalate.
    resolution = NeedsHumanResolution(
        resolvable=False, design_gated=False, decision="needs a human"
    )
    assert resolution_resolves(item=_item(), resolution=resolution) is False


def test_escalates_a_design_gated_block_even_at_high_confidence() -> None:
    # Scenario 36 leg 2: a drift-acceptance/spec-change/regroom decision is
    # reserved to a human even when the LLM could resolve it with high confidence.
    resolution = NeedsHumanResolution(
        resolvable=True, design_gated=True, decision="drift acceptance is human-owned"
    )
    assert resolution_resolves(item=_item(), resolution=resolution) is False


def test_escalates_a_human_only_item_even_when_resolvable() -> None:
    # Any `human-only` acceptance policy is a deliberate human gate: escalate.
    resolution = NeedsHumanResolution(resolvable=True, design_gated=False, decision="could resolve")
    item = _item(acceptance_policy="human-only")
    assert resolution_resolves(item=item, resolution=resolution) is False


def test_gate_name_is_needs_human() -> None:
    assert NEEDS_HUMAN_GATE == "needs-human"

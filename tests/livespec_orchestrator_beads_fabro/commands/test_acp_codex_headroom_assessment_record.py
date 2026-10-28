"""When the Codex assessment row is written, and what it is written without.

Binds the journal rule of "Admission filters Codex candidates by projected
usage-window headroom" in `SPECIFICATION/contracts.md` -- each assessed Codex
credential is journaled for each affected work-item -- to the writer's two
no-op conditions: a verdict resolved without a policy carries no floor and so
reported nothing, and a chain routed wholly away from Codex carries no Codex
assessment, so it earns no empty row. A chain routed wholly TO Codex carries no
Claude assessment and must still journal its Codex one.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom as codex
from livespec_orchestrator_beads_fabro.commands import _acp_codex_headroom_records as records
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

_NOW = "2026-10-28T06:00:00Z"


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _reading() -> codex.CodexHeadroomReading:
    return codex.unobservable_codex_headroom(
        credential_identity="codex-cred", observed_at=_NOW, reason="timed-out"
    )


def _verdict(*, floor: int | None, readings: tuple[codex.CodexHeadroomReading, ...]) -> Any:
    return AcpPreflightVerdict(
        fallback_enabled=True,
        session_headroom_floor_percent=floor,
        codex_headroom_assessments=readings,
    )


def test_a_codex_only_verdict_journals_its_codex_row_and_no_claude_row() -> None:
    journal = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-item",
        verdict=_verdict(floor=20, readings=(_reading(),)),
        journal=journal,
    )

    assert [record["stage"] for record in journal.records] == [codex.CODEX_HEADROOM_STAGE]
    assert journal.records[0] == records.codex_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(_reading(),)
    )
    assert journal.records[0]["provider"] == "codex"


def test_a_verdict_resolved_without_a_policy_journals_nothing() -> None:
    journal = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-item",
        verdict=_verdict(floor=None, readings=(_reading(),)),
        journal=journal,
    )

    assert journal.records == []


def test_a_verdict_with_no_assessment_of_either_provider_journals_nothing() -> None:
    journal = _Journal()

    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-item", verdict=_verdict(floor=0, readings=()), journal=journal
    )

    assert journal.records == []

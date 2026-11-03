"""Tests for the canonical factory-safety label vocabulary."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_safety_screen import (
    out_of_enum_factory_safety_refusal,
)
from livespec_orchestrator_beads_fabro.factory_safety import (
    FACTORY_SAFETY_REASONS,
    out_of_enum_factory_safety_finding,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, factory_safety: str | None) -> WorkItem:
    return WorkItem(
        id="bd-item",
        type="bug",
        status="ready",
        title="title",
        description="description",
        origin="direct",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-03T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="criteria",
        factory_safety=factory_safety,  # type: ignore[arg-type]
    )


def test_out_of_enum_factory_safety_finding_accepts_every_canonical_value() -> None:
    assert FACTORY_SAFETY_REASONS == (
        "needs-host-secrets",
        "mutates-host-machinery",
        "needs-privileged-host",
        "needs-host-only-input",
    )
    assert out_of_enum_factory_safety_finding(value=None) is None
    for reason in FACTORY_SAFETY_REASONS:
        assert out_of_enum_factory_safety_finding(value=reason) is None


def test_out_of_enum_factory_safety_finding_names_legacy_value_and_the_full_enum() -> None:
    finding = out_of_enum_factory_safety_finding(value="cross-repo-dev-tooling")

    assert finding is not None
    assert "cross-repo-dev-tooling" in finding
    for reason in FACTORY_SAFETY_REASONS:
        assert reason in finding


def test_prelaunch_screen_refuses_only_the_legacy_factory_safety_value() -> None:
    assert out_of_enum_factory_safety_refusal(items=[_item(factory_safety=None)]) is None
    assert (
        out_of_enum_factory_safety_refusal(items=[_item(factory_safety="needs-host-only-input")])
        is None
    )
    refusal = out_of_enum_factory_safety_refusal(
        items=[_item(factory_safety="cross-repo-dev-tooling")]
    )

    assert refusal is not None
    assert "bd-item" in refusal
    assert "cross-repo-dev-tooling" in refusal

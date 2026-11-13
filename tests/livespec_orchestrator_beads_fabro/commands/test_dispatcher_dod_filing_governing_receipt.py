"""Tests for the filing display's governing-only ledger receipt."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_filing_governing_receipt import (
    filing_governing_receipt,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_the_receipt_is_reusable_by_the_component_but_has_no_enclosing_outcome() -> None:
    """A filing-only taking cannot accidentally become a full DoD judgement."""
    receipt = filing_governing_receipt(
        item_id="bd-ib-3h7dsf",
        subject_digest="subject-digest",
        verdict=GoverningHeadingVerdict(kind="unstated"),
    )

    assert receipt.startswith("livespec-dod-judgement\n")
    assert "governing-heading-subject-digest: subject-digest" in receipt
    assert "outcome:" not in receipt


def test_a_sidecar_read_failure_still_takes_a_display_verdict(
    monkeypatch: object, tmp_path: object
) -> None:
    """The receipt write arm is skipped when there is no readable sidecar."""
    import importlib

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_governing_reading"
    )
    item = WorkItem(
        id="bd-ib-3h7dsf",
        type="bug",
        status="backlog",
        title="x",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="x",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    monkeypatch.setattr(
        module,
        "store_config",
        lambda **_: (_ for _ in ()).throw(
            module.BeadsCommandError(command="bd", exit_code=1, stderr="down")
        ),
    )
    monkeypatch.setattr(
        module,
        "host_governing_heading_taking_reader",
        lambda **_: lambda **_: module.GoverningHeadingTaking(
            verdict=GoverningHeadingVerdict(kind="unstated")
        ),
    )
    assert module.filing_governing_heading_reading(item=item, repo=tmp_path).verdict is not None

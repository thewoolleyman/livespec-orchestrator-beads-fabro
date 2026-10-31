"""Coverage controls for the classification-only command's report branches."""

from __future__ import annotations

import argparse

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_classify_tier as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_outcome import (
    SpecChangeTierOutcome,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    RecordedSpecChangeTier,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-child",
        type="task",
        status="blocked",
        title="A parked child",
        description="A disposition needs a recorded tier.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _args(*, item: str) -> argparse.Namespace:
    return argparse.Namespace(repo="/repo", item=item)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _recorded() -> RecordedSpecChangeTier:
    return RecordedSpecChangeTier(
        tier="none",
        classification="bug",
        verdict_kind="stated",
        generalization_target=None,
        linked_proposal_topic=None,
        spec_version="1",
        digest="digest",
    )


def test_the_command_reports_an_existing_record_and_refuses_an_unknown_item(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _item()
    monkeypatch.setattr(command, "load_items", lambda **_kwargs: [item])
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(
        command,
        "classify_item_spec_change_tier",
        lambda **_kwargs: SpecChangeTierOutcome(
            work_item_id=item.id, recorded=_recorded(), reused=True
        ),
    )

    assert command.run_classify_tier_command(args=_args(item=item.id)) == 0
    assert capsys.readouterr().out == "bd-ib-child: existing classification tier none\n"

    monkeypatch.setattr(command, "load_items", lambda **_kwargs: [])
    assert command.run_classify_tier_command(args=_args(item="bd-ib-missing")) == (
        EXIT_PRECONDITION_ERROR
    )
    assert "bd-ib-missing" in capsys.readouterr().err


def test_the_command_reports_when_the_shared_classifier_cannot_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _item()
    monkeypatch.setattr(command, "load_items", lambda **_kwargs: [item])
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(
        command,
        "classify_item_spec_change_tier",
        lambda **_kwargs: SpecChangeTierOutcome(
            work_item_id=item.id,
            recorded=None,
            cause="classification-answer-unreadable",
        ),
    )

    assert command.run_classify_tier_command(args=_args(item=item.id)) == 0
    assert capsys.readouterr().out == (
        "bd-ib-child: classification did not run (classification-answer-unreadable)\n"
    )

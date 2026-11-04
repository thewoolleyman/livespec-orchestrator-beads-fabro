"""Coverage controls for the classification-only command's report branches."""

from __future__ import annotations

import argparse

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_classify_tier as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
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


def test_the_command_refuses_an_unknown_item(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(command, "load_items", lambda **_kwargs: [])

    assert command.run_classify_tier_command(args=_args(item="bd-ib-missing")) == (
        EXIT_PRECONDITION_ERROR
    )
    assert "bd-ib-missing" in capsys.readouterr().err


def test_the_command_writes_nothing_when_the_ledger_comments_are_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _item()
    monkeypatch.setattr(command, "load_items", lambda **_kwargs: [item])
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: _config())
    monkeypatch.setattr(command, "item_comment_bodies", lambda **_kwargs: None)

    assert command.run_classify_tier_command(args=_args(item=item.id)) == EXIT_FAILURE
    assert "ledger comments unreadable" in capsys.readouterr().err

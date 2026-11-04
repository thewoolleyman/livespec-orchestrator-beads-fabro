"""Integration coverage for the failure paths of `clear-factory-safety`."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(*, factory_safety: str | None = "needs-host-secrets") -> WorkItem:
    return WorkItem(
        id="bd-ib-123",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        factory_safety=factory_safety,
    )


@pytest.mark.parametrize("rationale", ["", "   "])
def test_clear_factory_safety_refuses_missing_rationale_without_writing(
    tmp_path: Path, rationale: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    result = run_action(
        repo=repo,
        action_id=f"clear-factory-safety:bd-ib-123:{rationale}",
    )

    assert result["status"] == "failed"
    assert "missing rationale" in str(result["summary"])
    assert next(iter(read_work_items(path=_config()))).factory_safety == "needs-host-secrets"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-123") == ()
    assert not (repo / _JOURNAL).exists()


def test_clear_factory_safety_refuses_when_no_hold_is_set_without_writing(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(factory_safety=None))

    result = run_action(
        repo=repo,
        action_id="clear-factory-safety:bd-ib-123:the host-only work was superseded",
    )

    assert result["status"] == "failed"
    assert "no hold is set" in str(result["summary"])
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-123") == ()
    assert not (repo / _JOURNAL).exists()


def test_clear_factory_safety_without_a_rationale_field_is_not_a_write(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    result = run_action(repo=repo, action_id="clear-factory-safety:bd-ib-123")

    assert result["status"] == "failed"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-123") == ()
    assert not (repo / _JOURNAL).exists()

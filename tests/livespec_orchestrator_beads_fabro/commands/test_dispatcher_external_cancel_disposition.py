"""The disposition owed when a Fabro lifecycle cancel came from outside Dispatch."""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import outcome_class
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-external-cancel"
_RUN_ID = "01M5876JNZ3Q8E3W7G6MKE1FC7"
_FACTORY = "hp"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DISPOSITION_SOURCE = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_external_cancel_disposition.py"
)


class _ExternalCancelDisposition(Protocol):
    def dispose_external_fabro_cancel(
        self,
        *,
        repo: Path,
        item: WorkItem,
        outcome: DispatchOutcome,
        journal: JournalFile,
    ) -> None:
        """Persist the terminal external-cancel disposition."""


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A run cancelled by an operator",
        description="Rest an externally cancelled run for human triage.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The terminal cancellation is held for a human.",
    )
    return replace(base, **overrides)


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="cancelled",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="Pipeline cancelled",
        fabro_run_id=_RUN_ID,
        fabro_factory_name=_FACTORY,
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _disposition_module() -> _ExternalCancelDisposition:
    assert _DISPOSITION_SOURCE.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_external_cancel_disposition"
    )
    return cast(_ExternalCancelDisposition, module)


def _journal_stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_external_cancel_blocks_the_item_comments_the_factory_and_calibrates(
    tmp_path: Path,
) -> None:
    """The actual terminal-routing group owns this ending, not a side probe."""
    _ = _disposition_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)
    outcome = _outcome()

    dispose_terminal_routing(
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        now_iso="2026-10-19T00:01:00Z",
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    comments = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)

    assert outcome_class(outcome=outcome) == "cancelled:fabro-run"
    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert len(comments) == 1
    assert _RUN_ID in comments[0].text
    assert f"factory: {_FACTORY}" in comments[0].text
    assert "fabro-run-cancelled-blocked" in _journal_stages(journal=journal)


def test_non_cancelled_outcomes_do_not_take_the_external_cancel_route(tmp_path: Path) -> None:
    disposition = _disposition_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)

    disposition.dispose_external_fabro_cancel(
        repo=repo,
        item=item,
        outcome=replace(_outcome(), status="failed"),
        journal=journal,
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert stored.status == "active"
    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()
    assert _journal_stages(journal=journal) == []


def test_a_failed_block_write_is_journalled_without_a_misleading_comment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposition = _disposition_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)

    def _fail_block_write(**_kwargs: object) -> None:
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="unavailable")

    monkeypatch.setattr(disposition, "update_work_item_blocked_state", _fail_block_write)
    disposition.dispose_external_fabro_cancel(
        repo=repo,
        item=item,
        outcome=_outcome(),
        journal=journal,
    )

    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()
    assert "fabro-run-cancelled-blocked-error" in _journal_stages(journal=journal)


def test_a_failed_comment_write_is_journalled_after_the_item_is_safely_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposition = _disposition_module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)

    def _fail_comment_write(**_kwargs: object) -> None:
        raise BeadsCommandError(command="bd comment", exit_code=1, stderr="unavailable")

    monkeypatch.setattr(disposition, "append_work_item_comment", _fail_comment_write)
    disposition.dispose_external_fabro_cancel(
        repo=repo,
        item=item,
        outcome=_outcome(),
        journal=journal,
    )

    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert stored.status == "blocked"
    assert stored.blocked_reason == "needs-human"
    assert "fabro-run-cancelled-comment-error" in _journal_stages(journal=journal)

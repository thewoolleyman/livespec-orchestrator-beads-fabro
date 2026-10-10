"""Dispatch-scoped audit tests for the adopted factory-size ceiling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    record_size_justification,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    apply_factory_size_dispatch_entry,
    size_justified_at_admission,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="feature",
        status="ready",
        title="Factory size audit",
        description=(
            "## Definition of Done\n\n"
            "- The first assertion is verified.\n"
            "- The second assertion is verified.\n"
            "- The third assertion is verified.\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="factory-size-audit",
        prefix="factory-size-audit",
        server_user="factory-size-audit",
        database="factory-size-audit",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _write_ceiling(*, repo: Path, ceiling: int | None) -> None:
    dispatcher = {} if ceiling is None else {"adopted_assertion_count_ceiling": ceiling}
    (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _admit(*, repo: Path, config: StoreConfig, item: WorkItem, journal: JournalFile) -> None:
    result = apply_factory_size_dispatch_entry(
        cwd=repo,
        path_factory=lambda: config,
        items=(item,),
        journal=journal,
    )
    assert is_successful(result)
    assert unsafe_perform_io(result.unwrap()) == ()


def _dispatch(*, journal: JournalFile, item: WorkItem, dispatch_id: str) -> None:
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": item.id,
            "dispatch_id": dispatch_id,
        }
    )


def _records(*, journal: JournalFile) -> tuple[dict[str, object], ...]:
    return tuple(
        cast("dict[str, object]", json.loads(line))
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    )


def test_size_justification_is_attributed_to_the_exact_dispatch(
    tmp_path: Path,
) -> None:
    """Retries and interleaved items cannot inherit another admission decision."""
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(repo=repo)
    first = _item(item_id="bd-first")
    second = _item(item_id="bd-second")
    append_work_item(path=config, item=first)
    append_work_item(path=config, item=second)
    valid = {
        "rationale": "The larger slice is one coherent transaction.",
        "author": "human:maintainer",
        "at": "2026-10-10T00:00:00Z",
    }
    record_size_justification(
        path=config,
        work_item_id=first.id,
        justification=valid,
    )
    journal = JournalFile(path=repo / "dispatch.jsonl")

    _write_ceiling(repo=repo, ceiling=2)
    _admit(repo=repo, config=config, item=first, journal=journal)
    _dispatch(journal=journal, item=first, dispatch_id="dispatch-first-justified")

    _write_ceiling(repo=repo, ceiling=None)
    _admit(repo=repo, config=config, item=second, journal=journal)
    _dispatch(journal=journal, item=second, dispatch_id="dispatch-second-ordinary")
    _admit(repo=repo, config=config, item=first, journal=journal)
    _dispatch(journal=journal, item=first, dispatch_id="dispatch-first-ordinary")

    records = _records(journal=journal)
    assert (
        size_justified_at_admission(
            records=records,
            work_item_id=first.id,
            dispatch_id="dispatch-first-justified",
        )
        is True
    )
    assert (
        size_justified_at_admission(
            records=records,
            work_item_id=second.id,
            dispatch_id="dispatch-second-ordinary",
        )
        is False
    )
    assert (
        size_justified_at_admission(
            records=records,
            work_item_id=first.id,
            dispatch_id="dispatch-first-ordinary",
        )
        is False
    )
    assert (
        size_justified_at_admission(
            records=records,
            work_item_id=first.id,
            dispatch_id="dispatch-missing",
        )
        is None
    )

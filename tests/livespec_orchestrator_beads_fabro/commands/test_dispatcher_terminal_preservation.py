"""The terminal leg that preserves a run's work by pointer and then by tree.

WHAT IT MEANS FOR THIS LEG TO BE WRONG. The two preservations are the only
accounts of work a terminated run did not merge, and they carry DIFFERENT work:
the pointer names the terminal patch the run itself carried, while the tree is
the changed files nothing else carries once the engine's checkpoint commit
failed. So a leg that runs one and skips the other does not degrade gracefully
-- it loses exactly the half the other cannot stand in for.

WHY THE FAILURE ARMS ARE ASSERTED SEPARATELY PER LEG. The ratified clause says a
failed preservation "MUST NOT change the dispatch outcome or its exit code", and
the dangerous coupling is one leg's refusal suppressing the other's write. A
single test that only checked "nothing raised" would pass against an
implementation that abandoned the tree the moment the pointer failed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_terminal_preservation as preservation,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_preservation import (
    PRESERVE_BY_REFERENCE_ERROR_STAGE,
    PRESERVED_TREE_ERROR_STAGE,
    preserve_terminated_run_work,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-na2xvm"
_RUN = "01M4YJGC55V86C9V1X07QG3Y2H"
_CHECKPOINT_FAILED = "git checkpoint commit failed for node implement: git add failed (exit 127)"


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="blocked",
        title="A checkpoint-failed run's tree is published to a preservation ref",
        description="The tree nothing else carries.",
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
        blocked_reason="needs-human",
    )


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        fabro_bin="/home/ubuntu/.fabro/bin/fabro",
        fabro_factory_target=FactoryTarget(
            name="hp", server="https://hp-xubuntu.perch-rudd.ts.net:32276", dev_token=None
        ),
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"the run ended: {_CHECKPOINT_FAILED}",
        fabro_run_id=_RUN,
        fabro_failure_cause=_CHECKPOINT_FAILED,
    )


def _rows(*, journal_path: Path) -> list[dict[str, object]]:
    if not journal_path.is_file():
        return []
    return [
        json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line
    ]


def _run_leg(*, tmp_path: Path) -> list[dict[str, object]]:
    journal_path = tmp_path / "journal.jsonl"
    preserve_terminated_run_work(
        args=_args(),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=JournalFile(path=journal_path),
    )
    return _rows(journal_path=journal_path)


def test_both_preservations_run_and_the_pointer_goes_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Order matters and is the ratified one: the pointer is the cheaper and more
    # widely-owed leg, so a tree leg hanging on an unreachable factory must not
    # cost the pointer its write.
    called: list[str] = []

    def _pointer(**kwargs: object) -> None:
        _ = kwargs
        called.append("pointer")

    def _tree(**kwargs: object) -> None:
        _ = kwargs
        called.append("tree")

    monkeypatch.setattr(preservation, "preserve_checkpointed_work_reference", _pointer)
    monkeypatch.setattr(preservation, "preserve_checkpoint_failed_tree", _tree)
    _ = _run_leg(tmp_path=tmp_path)
    assert called == ["pointer", "tree"]


def test_a_refused_pointer_is_journaled_and_still_leaves_the_tree_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def _pointer(**kwargs: object) -> None:
        _ = kwargs
        raise OSError("the run record could not be read")

    def _tree(**kwargs: object) -> None:
        _ = kwargs
        called.append("tree")

    monkeypatch.setattr(preservation, "preserve_checkpointed_work_reference", _pointer)
    monkeypatch.setattr(preservation, "preserve_checkpoint_failed_tree", _tree)
    rows = _run_leg(tmp_path=tmp_path)
    # The tree leg still ran: one leg's refusal must not suppress the other.
    assert called == ["tree"]
    refused = [row for row in rows if row.get("stage") == PRESERVE_BY_REFERENCE_ERROR_STAGE]
    assert len(refused) == 1
    assert refused[0]["reason"] == "OSError"
    assert refused[0]["work_item_id"] == _ITEM


def test_a_refused_tree_preservation_is_journaled_and_never_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _pointer(**kwargs: object) -> None:
        _ = kwargs

    def _tree(**kwargs: object) -> None:
        _ = kwargs
        raise OSError("the factory could not be reached")

    monkeypatch.setattr(preservation, "preserve_checkpointed_work_reference", _pointer)
    monkeypatch.setattr(preservation, "preserve_checkpoint_failed_tree", _tree)
    rows = _run_leg(tmp_path=tmp_path)
    refused = [row for row in rows if row.get("stage") == PRESERVED_TREE_ERROR_STAGE]
    assert len(refused) == 1
    assert refused[0]["reason"] == "OSError"
    assert refused[0]["outcome_status"] == "blocked"

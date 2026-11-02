"""The shared row a host Definition-of-Done taking appends to the dispatch journal."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_journal import (
    journal_dod_taking,
    journal_dod_taking_to_repo,
)


class _Journal:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.rows.append(record)


def _ended() -> SimpleNamespace:
    return SimpleNamespace(
        spec_identity=None,
        deciding_candidate=None,
        bound_ended_candidates=("claude-acp:claude-sonnet-5-5",),
        total_input_tokens=100_321,
    )


def test_a_taking_with_neither_identity_nor_bound_evidence_appends_nothing() -> None:
    journal = _Journal()

    journal_dod_taking(
        journal=journal,
        work_item_id="bd-ib-x",
        stage="pre-dispatch",
        decision=SimpleNamespace(holds=False),
    )

    assert journal.rows == []


def test_a_caller_with_no_journal_appends_nothing() -> None:
    journal_dod_taking(
        journal=None, work_item_id="bd-ib-x", stage="pre-dispatch", decision=_ended()
    )


def test_a_bound_ended_taking_appends_its_stage_candidate_and_input_total() -> None:
    journal = _Journal()

    journal_dod_taking(
        journal=journal, work_item_id="bd-ib-x", stage="pre-admission", decision=_ended()
    )

    (row,) = journal.rows
    assert row["judgement_stage"] == "pre-admission"
    assert row["bound_ended_candidates"] == ["claude-acp:claude-sonnet-5-5"]
    assert row["total_input_tokens"] == 100_321


def test_the_repo_journal_receives_the_row_under_tmp(tmp_path: Path) -> None:
    journal_dod_taking_to_repo(
        repo=tmp_path, work_item_id="bd-ib-x", stage="pre-admission", decision=_ended()
    )

    lines = (tmp_path / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    (row,) = [json.loads(line) for line in lines.splitlines()]
    assert row["work_item_id"] == "bd-ib-x"
    assert row["total_input_tokens"] == 100_321

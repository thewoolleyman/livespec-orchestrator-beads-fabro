"""A withheld dispatch still journals every pre-launch step it ran."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_commands as module
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_FAILURE,
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from returns.io import IOSuccess

_ITEM = "bd-ib-n4kj4y"


def _arrange(
    monkeypatch: pytest.MonkeyPatch, *, journal: JournalFile, ledger_blocked: bool
) -> argparse.Namespace:
    monkeypatch.setattr(module, "pass_snapshot", contextlib.nullcontext)
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_: None)
    monkeypatch.setattr(module, "prepare", lambda **_: ([], journal))
    monkeypatch.setattr(module, "store_config", lambda **_: None)
    monkeypatch.setattr(module, "apply_factory_size_dispatch_entry", lambda **_: IOSuccess(()))
    monkeypatch.setattr(module, "ledger_blocked_after_normalization", lambda **_: ledger_blocked)
    monkeypatch.setattr(module, "ready_items", lambda **_: [])
    monkeypatch.setattr(module, "rework_redispatch_eligible_ids", lambda **_: set())
    return argparse.Namespace(item=_ITEM, repo=".", skip_ledger_check=False)


def _step_rows(*, journal: JournalFile) -> list[dict[str, object]]:
    if not journal.path.exists():
        return []
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return [row for row in rows if row.get("stage") == "pre-launch-step"]


def _assert_every_step_closed(*, rows: list[dict[str, object]], expected: list[str]) -> None:
    ends = [row for row in rows if row["event"] == "end"]
    assert [row["step"] for row in ends] == expected
    assert {row["step"] for row in rows if row["event"] == "start"} == set(expected)
    for row in ends:
        assert row["work_item_id"] == _ITEM
        assert isinstance(row["elapsed_seconds"], float)
        assert row["outcome"]


def test_a_missing_target_withholds_the_dispatch_after_journaling_every_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Target selection returns nothing; the earlier steps' rows still land."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    args = _arrange(monkeypatch, journal=journal, ledger_blocked=False)

    assert module.run_dispatch_command(args=args) == EXIT_PRECONDITION_ERROR

    _assert_every_step_closed(
        rows=_step_rows(journal=journal),
        expected=[
            "drive-startup",
            "dispatch-preamble",
            "otel-egress",
            "ledger-prepare",
            "factory-size-check",
            "ledger-check",
            "target-selection",
        ],
    )


def test_a_ledger_block_withholds_the_dispatch_after_journaling_every_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The ledger check blocks before selection; the steps up to it still land."""
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    args = _arrange(monkeypatch, journal=journal, ledger_blocked=True)

    assert module.run_dispatch_command(args=args) == EXIT_FAILURE

    _assert_every_step_closed(
        rows=_step_rows(journal=journal),
        expected=[
            "drive-startup",
            "dispatch-preamble",
            "otel-egress",
            "ledger-prepare",
            "factory-size-check",
            "ledger-check",
        ],
    )

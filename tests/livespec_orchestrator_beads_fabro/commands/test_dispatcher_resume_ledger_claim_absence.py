"""Ledger claim fallback leaves a genuinely absent claim without a run identifier."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_resume_observation as observation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-oknwxm"


@dataclass(frozen=True, kw_only=True)
class _ForgeReading:
    """A readable forge answer that names no pull request."""

    observed: bool = True
    pull_request: None = None


@dataclass(frozen=True, kw_only=True)
class _FactoryReading:
    """A readable factory answer that names no earlier run."""

    earlier_run_succeeded: bool = False
    executing_node: None = None
    live_runs: tuple[()] = ()
    observed: bool = True


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="An item whose ledger has no earlier dispatch claim",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _write_config(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                }
            }
        ),
        encoding="utf-8",
    )


def test_a_readable_ledger_row_without_a_claim_adds_no_earlier_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty claim is distinct from a ledger-derived terminal-ref candidate."""
    _write_config(repo=tmp_path)
    monkeypatch.setattr(observation, "publish_branch_for", lambda **_: "feat/bd-ib-oknwxm")
    monkeypatch.setattr(observation, "branch_pull_request", lambda **_: _ForgeReading())
    monkeypatch.setattr(observation, "read_journal_records", lambda **_: ())
    monkeypatch.setattr(observation, "cancel_anchor", lambda **_: None)
    monkeypatch.setattr(observation, "resume_anchor", lambda **_: None)
    monkeypatch.setattr(observation, "factory_reading", lambda **_: _FactoryReading())
    monkeypatch.setattr(
        observation,
        "claim_row_for",
        lambda **_: ClaimRow(status="ready", assignee=None, stamp=None),
    )

    gather = observation.gather_resume(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal_path=tmp_path / "journal.jsonl",
        runner=ShellCommandRunner(),
    )

    assert gather.earlier_run_ids == ()

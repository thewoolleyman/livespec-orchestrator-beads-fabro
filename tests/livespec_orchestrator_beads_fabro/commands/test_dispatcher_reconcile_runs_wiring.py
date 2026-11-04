"""Tests pinning where the automatic reconciliation pass runs on the dispatch path.

The pass has ONE call site — the tail of `dispatch_preamble` — because the
preamble is the head of every `dispatch` AND of every `loop` iteration. These
tests pin both readings of that single call: the loop reconciles once per tick
BEFORE it selects a candidate, and the preamble reconciles before admission
without ever converting a reconciliation failure into a dispatch refusal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_command as loop_command
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_reconcile_runs_pass as reconcile_pass,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_checks as run_checks
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble, main
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_the_loop_reconciles_once_per_tick_before_it_selects_anything(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    order: list[str] = []

    def _reconcile(*, args: argparse.Namespace, repo: Path) -> object:
        _ = (args, repo)
        order.append("reconcile-runs-pass")
        return object()

    def _candidates(
        *, args: argparse.Namespace, items: list[WorkItem], repo: Path, journal: object
    ) -> list[Any]:
        _ = (args, items, repo, journal)
        order.append("candidates")
        return []

    monkeypatch.setattr(run_checks, "reconcile_runs_pass", _reconcile)
    monkeypatch.setattr(loop_command, "candidates", _candidates)
    monkeypatch.setattr(loop_command, "arm_otel_egress", lambda **_: None)
    monkeypatch.setattr(
        loop_command,
        "prepare",
        lambda **_: ([], JournalFile(path=repo / "journal.jsonl")),
    )

    exit_code = main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "1",
            "--fabro-bin",
            str(_fabro_bin(tmp_path=tmp_path)),
            "--skip-ledger-check",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    # Order, not merely presence: reconciling AFTER selection would let the
    # tick pick work against an inventory it has not yet reconciled.
    assert order == ["reconcile-runs-pass", "candidates"]


def test_the_preamble_reconciles_exactly_once_and_proceeds(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    calls: list[Path] = []

    def _reconcile(*, args: argparse.Namespace, repo: Path) -> object:
        _ = args
        calls.append(repo)
        return object()

    monkeypatch.setattr(run_checks, "reconcile_runs_pass", _reconcile)
    args = argparse.Namespace(
        fabro_bin=str(_fabro_bin(tmp_path=tmp_path)),
        janitor=None,
        journal=None,
    )

    janitor, exit_code = dispatch_preamble(args=args, repo=repo)

    assert (janitor, exit_code) == (None, None)
    assert calls == [repo]


def test_a_reconciliation_failure_is_journaled_and_the_dispatch_still_proceeds(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reconciliation is not a dispatch precondition (contracts.md).

    This runs the REAL pass through the REAL preamble, with only the factory
    survey made to fail, so the fail-open guarantee is proven where a dispatch
    would actually feel it rather than in the pass's own unit.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"

    def _explode(*, repo: Path, factory: str | None = None) -> tuple[FactoryTarget, ...]:
        _ = (repo, factory)
        raise BeadsConnectionError(detail="tenant unreachable")

    monkeypatch.setattr(reconcile_pass, "reconcile_factory_targets", _explode)
    args = argparse.Namespace(
        fabro_bin=str(_fabro_bin(tmp_path=tmp_path)),
        janitor=None,
        journal=str(journal),
    )

    janitor, exit_code = dispatch_preamble(args=args, repo=repo)

    assert (janitor, exit_code) == (None, None)
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    passes = [record for record in records if record["stage"] == "reconcile-runs-pass"]
    assert len(passes) == 1
    assert passes[0]["errors"] == 1
    assert "BeadsConnectionError" in passes[0]["failure_detail"]


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _fabro_bin(*, tmp_path: Path) -> Path:
    path = tmp_path / "fabro"
    _ = path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path

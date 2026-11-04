"""The admission filter consults the across-dispatch progress gate before a claim.

The gate itself is graded in `test_dispatcher_redispatch_gate*`; this module
proves the eligibility ladder actually reaches it, and reaches it only for a
row every earlier condition admitted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_redispatch_gate as gate
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-ladder"


class _FlatFactory:
    def __init__(self, *, repo: Path, journal: JournalFile) -> None:
        _ = (repo, journal)

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        _ = (factory, run_id)
        outcomes = {
            "dod_gate": {"status": "succeeded"},
            "implement": {"status": "failed", "failure": {"causes": ["flat"]}},
        }
        return [{"status": {"kind": "failed"}, "checkpoint": {"node_outcomes": outcomes}}]


def _fixture(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs: int
) -> tuple[Path, JournalFile, WorkItem]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    monkeypatch.setattr(gate, "FactoryRunReader", _FlatFactory)
    repo = tmp_path / "repo"
    repo.mkdir()
    connection = {
        "tenant": "livespec-impl-beads",
        "prefix": "livespec-impl-beads",
        "server_user": "livespec-impl-beads",
        "database": "livespec-impl-beads",
        "bd_path": "bd",
        "fake": True,
    }
    config = {
        "livespec-orchestrator-beads-fabro": {
            "connection": connection,
            "dispatcher": {"redispatch_no_progress_limit": 1},
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    store = StoreConfig(**connection, repo_root=repo)  # type: ignore[arg-type]
    item = WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="Ladder candidate",
        description="## Definition of Done\n\n- One assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )
    append_work_item(path=store, item=item)
    journal = JournalFile(path=repo / "journal.jsonl")
    for index in range(runs):
        journal.append(
            record={
                "stage": "dispatch-run-stamp",
                "work_item_id": _ITEM,
                "run_id": f"RUN{index}",
                "dispatch_factory": "petri",
            }
        )
    return repo, journal, item


def test_a_repeated_flat_history_is_refused_by_the_filter_before_a_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Baseline plus one flat attributable terminal reaches a limit of one."""
    repo, journal, item = _fixture(tmp_path=tmp_path, monkeypatch=monkeypatch, runs=2)
    preflight = AcpPreflightVerdict(fallback_enabled=True, success_critical=("implement",))
    admittable, refused = filter_eligible_candidates(
        repo=repo, preflight=preflight, candidates=[item], journal=journal
    )
    assert admittable == []
    assert [outcome.stage for outcome in refused] == ["redispatch-no-progress"]


def test_a_single_earlier_run_is_only_a_baseline_and_admits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first observed terminal establishes the baseline and counts for nothing."""
    repo, journal, item = _fixture(tmp_path=tmp_path, monkeypatch=monkeypatch, runs=1)
    preflight = AcpPreflightVerdict(fallback_enabled=True, success_critical=("implement",))
    admittable, refused = filter_eligible_candidates(
        repo=repo, preflight=preflight, candidates=[item], journal=journal
    )
    assert [candidate.id for candidate in admittable] == [_ITEM]
    assert refused == []

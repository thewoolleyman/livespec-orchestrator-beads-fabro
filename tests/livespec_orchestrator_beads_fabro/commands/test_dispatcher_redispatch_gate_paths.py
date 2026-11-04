"""The gate's refusal arms, recovery selection, default readers and consumption."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_redispatch_gate as gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_recovery_record import (
    render_consumed_comment,
    render_recovery_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-s5idxj"
_GRAPH = """digraph g {
  start [shape=Mdiamond]
  implement [shape=box]
  review [shape=box]
  exit [shape=Msquare]
  start -> implement
  implement -> review
  review -> exit
}
"""


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(root: Path, *, limit: int | None = 2) -> Path:
    dispatcher: dict[str, object] = {} if limit is None else {"redispatch_no_progress_limit": limit}
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    _ = (root / "workflow.toml").write_text('[workflow]\ngraph = "graph.dot"\n', encoding="utf-8")
    _ = (root / "graph.dot").write_text(_GRAPH, encoding="utf-8")
    return root


def _journal(repo: Path, runs: Sequence[str], *, detail: str = "review failed") -> JournalFile:
    rows: list[dict[str, object]] = []
    for run_id in runs:
        rows.extend(
            (
                {
                    "stage": "dispatch-id",
                    "work_item_id": _ITEM,
                    "dispatch_id": f"d-{run_id}",
                    "workflow_toml": str(repo / "workflow.toml"),
                },
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": _ITEM,
                    "run_id": run_id,
                    "dispatch_id": f"d-{run_id}",
                    "dispatch_factory": "petri",
                },
                {
                    "stage": "outcome",
                    "outcome": {
                        "work_item_id": _ITEM,
                        "status": "blocked",
                        "fabro_run_id": run_id,
                        "detail": detail,
                    },
                },
            )
        )
    path = repo / f"journal-{len(runs)}-{abs(hash(detail))}.jsonl"
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _flat(_factory: str, _run: str) -> object | None:
    outcomes = {"implement": {"status": "succeeded"}, "review": {"status": "failed"}}
    return [{"status": "failed", "checkpoint": {"node_outcomes": outcomes}}]


def _blind(_factory: str, _run: str) -> object | None:
    return None


def _recovery(attempt_id: str, prior: tuple[str, ...], *, diagnosis: str = "measured") -> str:
    return render_recovery_comment(
        recovery=RedispatchRecovery(
            attempt_id=attempt_id,
            prior_run_ids=prior,
            diagnosis=diagnosis,
            operation="dispatch",
            execution_evidence="receipt",
        )
    )


def _ask(
    repo: Path,
    journal: JournalFile,
    *,
    reader: gate.RunPayloadReader = _flat,
    bodies: Sequence[str] | str = (),
    authorized: list[tuple[str, str]] | None = None,
) -> str | None:
    return gate.redispatch_progress_refusal(
        repo=repo,
        items=(_item(),),
        journal=journal,
        run_payload=reader,
        comment_bodies=lambda _item: bodies,
        authorized=[] if authorized is None else authorized,
    )


def test_an_empty_selection_reads_nothing(tmp_path: Path) -> None:
    """The drain's idle pass owes no journal read."""
    refusal = gate.redispatch_progress_refusal(
        repo=tmp_path, items=(), journal=JournalFile(path=tmp_path / "absent"), authorized=[]
    )
    assert refusal is None


def test_history_with_an_invalid_limit_or_unreadable_ledger_refuses(tmp_path: Path) -> None:
    """Policy and ledger faults are named instead of being counted around."""
    journal = _journal(_repo(tmp_path, limit=None), ("r1", "r2"))
    policy = _ask(tmp_path, journal)
    assert policy is not None
    assert policy.startswith("LIVESPEC_REDISPATCH_POLICY_INVALID")
    ledger = _ask(_repo(tmp_path), journal, bodies="bd comments failed")
    assert ledger is not None
    assert ledger.startswith("LIVESPEC_REDISPATCH_LEDGER_UNREADABLE")
    assert "bd comments failed" in ledger


def test_an_unknown_cause_requires_diagnosis_and_a_recovery_naming_the_history(
    tmp_path: Path,
) -> None:
    """Unknown causes refuse; one fresh recovery over the whole history admits one dispatch."""
    repo = _repo(tmp_path)
    journal = _journal(repo, ("r1", "r2"))
    refusal = _ask(repo, journal, reader=_blind)
    assert refusal is not None
    assert "LIVESPEC_REDISPATCH_DIAGNOSIS_REQUIRED" in refusal
    assert "--prior-run r1" in refusal
    assert "--prior-run r2" not in refusal

    authorized: list[tuple[str, str]] = []
    admitted = _ask(
        repo, journal, reader=_blind, bodies=[_recovery("rec", ("r1",))], authorized=authorized
    )
    assert admitted is None
    assert authorized == [(_ITEM, "rec")]


def test_a_spent_diagnosis_recovery_leaves_a_diagnosed_baseline(tmp_path: Path) -> None:
    """After the epoch is spent the diagnosed run no longer re-diagnoses every dispatch."""
    repo = _repo(tmp_path)
    journal = _journal(repo, ("r1",))
    spent = [_recovery("rec", ("r1",)), render_consumed_comment(attempt_id="rec")]
    authorized: list[tuple[str, str]] = []
    assert _ask(repo, journal, reader=_blind, bodies=spent, authorized=authorized) is None
    assert authorized == []


def test_recovery_selection_skips_unfit_recoveries_and_refuses_a_stale_history(
    tmp_path: Path,
) -> None:
    """A recovery naming an older history, or an empty field, never admits the item."""
    repo = _repo(tmp_path)
    journal = _journal(repo, ("r1", "r2", "r3", "r4"))
    stale = _recovery("old", ("r2", "r3"))
    blank = _recovery("blank", ("r2", "r3", "r4"), diagnosis="")
    authorized: list[tuple[str, str]] = []
    refusal = _ask(repo, journal, bodies=[stale, blank], authorized=authorized)
    assert refusal is not None
    assert "r2 (review failed), r3 (review failed), r4 (review failed)" in refusal
    assert authorized == []


def test_the_unrefused_candidates_drop_only_the_refused_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One refused row never stops the queue behind it."""
    repo = _repo(tmp_path)
    journal = _journal(repo, ("r1", "r2", "r3"))
    other = replace(_item(), id="bd-ib-other")
    monkeypatch.setattr(gate, "_factory_payload", lambda **_: _flat)
    monkeypatch.setattr(gate, "_ledger_bodies", lambda **_: lambda _item: ())
    kept = gate.redispatch_unrefused_candidates(items=[_item(), other], repo=repo, journal=journal)
    assert kept == [other]


def test_the_default_readers_use_the_factory_reader_and_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no seams, evidence comes from the recorded factory and the item's comments."""
    repo = _repo(tmp_path)
    journal = _journal(repo, ("r1", "r2", "r3"))
    asked: list[tuple[str, str]] = []

    def inspect_payload(_self: object, *, factory: str, run_id: str) -> object | None:
        asked.append((factory, run_id))
        return _flat(factory, run_id)

    class _Comment:
        def __init__(self, text: str) -> None:
            self.text = text

    monkeypatch.setattr(gate.FactoryRunReader, "inspect_payload", inspect_payload)
    monkeypatch.setattr(gate, "read_dispatch_comments", lambda **_: (_Comment("prose"),))
    refusal = gate.redispatch_progress_refusal(
        repo=repo, items=(_item(),), journal=journal, authorized=[]
    )
    assert refusal is not None
    assert asked == [("petri", "r1"), ("petri", "r2"), ("petri", "r3")]

    monkeypatch.setattr(gate, "read_dispatch_comments", lambda **_: "ledger down")
    unreadable = gate.redispatch_progress_refusal(
        repo=repo, items=(_item(),), journal=journal, authorized=[]
    )
    assert unreadable is not None
    assert "LIVESPEC_REDISPATCH_LEDGER_UNREADABLE" in unreadable


def test_consuming_a_recovery_appends_one_comment_per_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spend is an append-only ledger comment naming the attempt id."""
    written: list[tuple[str, str]] = []
    monkeypatch.setattr(gate, "store_config", lambda **_: "config")
    monkeypatch.setattr(
        gate,
        "append_work_item_comment",
        lambda *, work_item_id, body, **_: written.append((work_item_id, body)),
    )
    gate.consume_authorized_recoveries(repo=tmp_path, authorized=[(_ITEM, "rec")])
    assert written == [(_ITEM, render_consumed_comment(attempt_id="rec"))]

"""The pre-claim gate refuses an item whose recorded history stopped advancing.

Scenario 151: each completed attempt is compared with the high-water mark that
preceded it, using the workflow graph's own dependency order and the evidence of
the factory recorded for that run.  Every refusal below is paired with a control
history that must be admitted, because a gate refusing everything would satisfy
the refusals alone.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_gate import (
    redispatch_progress_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    RedispatchRecovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_recovery_record import (
    render_recovery_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-s5idxj"
_GRAPH = """digraph g {
  start [shape=Mdiamond]
  implement [shape=box]
  review [shape=box]
  pr [shape=box]
  exit [shape=Msquare]
  needs_human [shape=parallelogram]
  start -> implement
  implement -> review
  review -> pr
  pr -> exit
  review -> needs_human
}
"""


def test_flat_attributable_history_refuses_before_claim_naming_its_evidence(
    tmp_path: Path,
) -> None:
    """A baseline plus two flat item failures exhaust a limit of two."""
    repo = _repo(tmp_path, limit=2)
    journal = _journal(repo, runs=("r1", "r2", "r3"))
    reached = {"r1": "implement", "r2": "implement", "r3": "implement"}
    refusal = _refusal(repo, journal, reached=reached)

    assert refusal is not None
    assert "r2 (review failed), r3 (review failed)" in refusal
    assert "high-water milestone: implement" in refusal
    assert "r1" not in refusal
    assert "typed causal recovery" in refusal


def test_advancing_history_and_an_empty_history_are_admitted(tmp_path: Path) -> None:
    """Controls: progress resets the count, and a first dispatch needs no policy."""
    repo = _repo(tmp_path, limit=2)
    advancing = _journal(repo, runs=("r1", "r2", "r3"))
    reached = {"r1": "implement", "r2": "implement", "r3": "review"}
    assert _refusal(repo, advancing, reached=reached) is None

    fresh = JournalFile(path=tmp_path / "fresh.jsonl")
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _refusal(bare, fresh, reached={}) is None


def test_missing_policy_refuses_with_a_configuration_diagnostic(tmp_path: Path) -> None:
    """History with no committed limit never receives an implicit count."""
    repo = _repo(tmp_path, limit=None)
    journal = _journal(repo, runs=("r1", "r2"))
    refusal = _refusal(repo, journal, reached={"r1": "implement", "r2": "implement"})

    assert refusal is not None
    assert "dispatcher.redispatch_no_progress_limit" in refusal


def test_a_fresh_typed_recovery_authorizes_one_epoch_and_is_not_replayable(
    tmp_path: Path,
) -> None:
    """The recovery clears the refusal once; a consumed id stays spent."""
    repo = _repo(tmp_path, limit=2)
    journal = _journal(repo, runs=("r1", "r2", "r3"))
    reached = {"r1": "implement", "r2": "implement", "r3": "implement"}
    recovery = RedispatchRecovery(
        attempt_id="recovery-1",
        prior_run_ids=("r2", "r3"),
        diagnosis="the review fixture is stale",
        operation="dispatch --item bd-ib-s5idxj",
        execution_evidence="receipt-1",
    )
    bodies = [render_recovery_comment(recovery=recovery)]
    authorized: list[tuple[str, str]] = []

    admitted = _refusal(repo, journal, reached=reached, bodies=bodies, authorized=authorized)
    assert admitted is None
    assert authorized == [(_ITEM, "recovery-1")]

    spent = [*bodies, 'livespec-redispatch-recovery-consumed\n{"attempt_id": "recovery-1"}']
    assert _refusal(repo, journal, reached=reached, bodies=spent) is not None


def _refusal(
    repo: Path,
    journal: JournalFile,
    *,
    reached: dict[str, str],
    bodies: list[str] | None = None,
    authorized: list[tuple[str, str]] | None = None,
) -> str | None:
    return redispatch_progress_refusal(
        repo=repo,
        items=(_work_item(),),
        journal=journal,
        run_payload=lambda _factory, run_id: _payload(reached=reached.get(run_id)),
        comment_bodies=lambda _item: [] if bodies is None else bodies,
        authorized=[] if authorized is None else authorized,
    )


def _payload(*, reached: str | None) -> list[dict[str, object]]:
    order = ("implement", "review", "pr")
    done = order[: order.index(reached) + 1] if reached is not None else ()
    outcomes: dict[str, dict[str, str]] = {node: {"status": "succeeded"} for node in done}
    failed = "pr" if reached == "review" else "review"
    outcomes[failed] = {"status": "failed"}
    return [{"status": "failed", "checkpoint": {"node_outcomes": outcomes}}]


def _repo(root: Path, *, limit: int | None) -> Path:
    dispatcher: dict[str, object] = {} if limit is None else {"redispatch_no_progress_limit": limit}
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    _ = (root / "workflow.toml").write_text('[workflow]\ngraph = "graph.dot"\n', encoding="utf-8")
    _ = (root / "graph.dot").write_text(_GRAPH, encoding="utf-8")
    return root


def _journal(repo: Path, *, runs: tuple[str, ...]) -> JournalFile:
    path = repo / "journal.jsonl"
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
                        "stage": "fabro-run",
                        "fabro_run_id": run_id,
                        "detail": "review failed",
                    },
                },
            )
        )
    _ = path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _work_item() -> WorkItem:
    base = WorkItem(
        id=_ITEM,
        type="task",
        status="ready",
        title="title",
        description="Do the thing.",
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
    return replace(base)

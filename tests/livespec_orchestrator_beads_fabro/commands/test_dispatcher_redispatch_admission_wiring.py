"""Where the across-dispatch gate sits: the eligibility ladder and recovery routing.

Edges of the gate's own grading live here too: a refusal must say WHY it is a
diagnosis, a configuration fault must precede any factory read, and a control
history must still be admitted or the rule is a universal refusal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands import _dispatcher_redispatch_admission as gate
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import ROUTE_FRESH
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    redispatch_progress_decision,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-sample"
_GRAPH = """digraph G {
  start [shape=Mdiamond]
  implement [shape=parallelogram]
  review [shape=parallelogram]
  start -> implement
  implement -> review
}
"""
_PARTIAL = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: the implement turn left work incomplete"


class _Runs:
    def __init__(self, *, succeeded: dict[str, tuple[str, ...]]) -> None:
        self.succeeded = succeeded

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        _ = factory
        nodes = self.succeeded.get(run_id)
        if nodes is None:
            return None
        return [{"checkpoint": {"node_outcomes": {n: {"status": "succeeded"} for n in nodes}}}]


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="Sample",
        description="## Definition of Done\n\n- It works.\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _repo(*, tmp_path: Path, limit: object = 2) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"redispatch_no_progress_limit": limit},
                }
            }
        ),
        encoding="utf-8",
    )
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n', encoding="utf-8"
    )
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return tmp_path


def _terminal(*, journal: JournalFile, run_id: str, detail: str = _PARTIAL) -> None:
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM_ID,
                "status": "blocked",
                "stage": "fabro-run",
                "fabro_run_id": run_id,
                "fabro_factory_name": "petri",
                "detail": detail,
                "needs_human_kind": "stage-failure",
                "needs_human_stages": ["implement"],
            },
        }
    )


def _journal(*, tmp_path: Path, runs: tuple[str, ...]) -> JournalFile:
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    for run_id in runs:
        _terminal(journal=journal, run_id=run_id)
    return journal


def _recovery(*, journal: JournalFile, **fields: object) -> None:
    journal.append(
        record={
            "stage": "redispatch-recovery",
            "work_item_id": _ITEM_ID,
            "attempt_id": "recovery-1",
            "prior_run_ids": ["01B", "01C"],
            "diagnosis": "ran out of turn budget",
            "operation": f"impl:{_ITEM_ID}",
            "execution_evidence": "resume from preserved tree",
            **fields,
        }
    )


def _flat() -> _Runs:
    return _Runs(succeeded={"01A": ("implement",), "01B": ("start",), "01C": ("start",)})


@pytest.mark.parametrize("limit", [0, -1, True, "3", None])
def test_an_invalid_limit_is_a_configuration_refusal_before_any_factory_read(
    tmp_path: Path, limit: object
) -> None:
    repo = _repo(tmp_path=tmp_path, limit=limit)
    journal = _journal(tmp_path=tmp_path, runs=("01A",))

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_Runs(succeeded={})
    )

    assert refusal is not None
    assert refusal.stage == "configuration"
    assert "positive committed integer" in refusal.detail


def test_an_unparseable_config_is_reported_as_unreadable(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text("{not json", encoding="utf-8")
    journal = _journal(tmp_path=tmp_path, runs=("01A",))

    refusal = gate.redispatch_progress_refusal(repo=tmp_path, item=_item(), journal=journal)

    assert refusal is not None
    assert "unreadable" in refusal.detail


def test_a_milestone_that_cannot_be_read_requires_diagnosis_not_a_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B"))

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_Runs(succeeded={})
    )

    assert refusal is not None
    assert refusal.stage == "redispatch-diagnosis-required"
    assert "01A" in refusal.detail


def test_an_unreadable_workflow_graph_requires_diagnosis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)

    def _no_ranks(*, repo: Path) -> None:
        _ = repo

    monkeypatch.setattr(gate, "committed_node_ranks", _no_ranks)
    journal = _journal(tmp_path=tmp_path, runs=("01A",))

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat()
    )

    assert refusal is not None
    assert refusal.stage == "redispatch-diagnosis-required"


def test_histories_from_incomparable_variants_require_diagnosis(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B"))
    runs = _Runs(succeeded={"01A": ("implement",), "01B": ("legacy_stage", "implement")})

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=runs
    )

    assert refusal is not None
    assert refusal.stage == "redispatch-diagnosis-required"
    assert "undeclared:legacy_stage" in refusal.detail


def test_an_unknown_terminal_cause_requires_diagnosis(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM_ID,
                "status": "failed",
                "fabro_run_id": "01A",
                "fabro_factory_name": "petri",
                "detail": "unclassified",
            },
        }
    )

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat()
    )

    assert refusal is not None
    assert "unknown terminal cause" in refusal.detail


def test_a_stale_or_incomplete_recovery_does_not_authorize(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    _recovery(journal=journal, execution_evidence="")

    incomplete = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat()
    )
    _recovery(journal=journal, attempt_id="recovery-2", prior_run_ids=["01B"])
    wrong_history = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat()
    )
    _recovery(journal=journal, attempt_id="recovery-3", operation="try a different approach")
    prose = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=_flat()
    )

    assert incomplete is not None
    assert "execution evidence" in incomplete.detail
    assert wrong_history is not None
    assert "refused non-progress run history" in wrong_history.detail
    assert prose is not None
    assert "executable operation" in prose.detail


def test_a_spent_recovery_does_not_hide_runs_added_after_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    _recovery(journal=journal)
    journal.append(record={"stage": "dispatch-id", "work_item_id": _ITEM_ID})
    _terminal(journal=journal, run_id="01D")
    runs = _Runs(succeeded={**_flat().succeeded, "01D": ("start",)})

    refusal = gate.redispatch_progress_refusal(
        repo=repo, item=_item(), journal=journal, factory_runs=runs
    )

    assert refusal is not None
    assert refusal.stage == "redispatch-no-progress"
    assert "01D" in refusal.detail
    assert "01B" in refusal.detail


def test_the_default_reader_is_the_recorded_factory_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A",))
    built: list[Path] = []

    class _Reader(_Runs):
        def __init__(self, *, repo: Path) -> None:
            super().__init__(succeeded={"01A": ("implement",)})
            built.append(repo)

    monkeypatch.setattr(gate, "FactoryRunReader", _Reader)

    assert gate.redispatch_progress_refusal(repo=repo, item=_item(), journal=journal) is None
    assert built == [repo]


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _filter(*, repo: Path, journal: JournalFile, runs: _Runs) -> tuple[list[WorkItem], list[str]]:
    admittable, refused = filter_eligible_candidates(
        repo=repo,
        preflight=AcpPreflightVerdict(fallback_enabled=True, success_critical=("implement",)),
        candidates=[_item()],
        journal=journal,
        factory_runs=runs,
    )
    return admittable, [outcome.stage for outcome in refused]


def test_the_eligibility_ladder_refuses_a_flat_history_and_admits_a_normal_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(repo_root=repo), item=_item())
    flat = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))

    refused = _filter(repo=repo, journal=flat, runs=_flat())
    admitted_control = _filter(
        repo=repo,
        journal=flat,
        runs=_Runs(succeeded={"01A": ("start",), "01B": ("implement",), "01C": ("review",)}),
    )

    assert refused == ([], ["redispatch-no-progress"])
    assert [item.id for item in admitted_control[0]] == [_ITEM_ID]
    assert admitted_control[1] == []


def _refused(**kwargs: object) -> gate.RedispatchGrade:
    _ = kwargs
    return gate.RedispatchGrade(stage="redispatch-no-progress", detail="refused")


def _admitted(**kwargs: object) -> None:
    _ = kwargs


def test_recovery_routing_grades_the_refusal_before_it_routes_a_released_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, runs=("01A", "01B", "01C"))
    measured: list[str] = []

    def _gather(**kwargs: object) -> object:
        _ = kwargs
        measured.append("gathered")
        raise _MeasuredError

    monkeypatch.setattr(routing, "gather_resume", _gather)
    monkeypatch.setattr(
        routing,
        "grade_redispatch_progress",
        _refused,
    )

    result = routing.route_recovery(
        args=argparse.Namespace(), repo=repo, candidates=[_item()], journal=journal
    )

    assert [route.route for route in result.routes] == [ROUTE_FRESH]
    assert measured == []

    monkeypatch.setattr(routing, "grade_redispatch_progress", _admitted)
    with pytest.raises(_MeasuredError):
        routing.route_recovery(
            args=argparse.Namespace(), repo=repo, candidates=[_item()], journal=journal
        )
    assert measured == ["gathered"]


class _MeasuredError(Exception):
    """Raised by the stand-in measurement so the test sees it was reached."""


def _attempt(*, run_id: str, order: int, attributable: bool = True) -> CompletedAttempt:
    return CompletedAttempt(
        run_id=run_id,
        terminal_cause="cause",
        high_water_milestone=f"m{order}",
        item_attributable=attributable,
        high_water_order=order,
    )


def test_a_host_failure_never_establishes_the_baseline_and_late_runs_are_counted() -> None:
    attempts = (
        _attempt(run_id="host", order=9, attributable=False),
        _attempt(run_id="base", order=1),
        _attempt(run_id="flat-1", order=1),
        _attempt(run_id="flat-2", order=0),
        _attempt(run_id="flat-3", order=1),
    )

    decision = redispatch_progress_decision(limit=2, attempts=attempts)

    assert decision.refusal is not None
    assert decision.refusal.run_ids == ("flat-1", "flat-2", "flat-3")
    assert decision.refusal.high_water_milestone == "m1"

"""Tests for the dead-implementer truncation journal record (bd-ib-8nnu).

The workflow's circuit breaker already refuses to spend a second vendor on an
unchanged tree. These tests pin the OBSERVABILITY obligation that the provider-spend-containment
contract in `SPECIFICATION/contracts.md` places on the Dispatcher: the
truncation is an auto-disposition, so it must be journaled with the work-item
id and the governing condition, and it must not read as an ordinary implementer
failure.

The sentinel strings are copied verbatim from
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`, because a
paraphrase would be a probe that cannot return a hit against the real output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    DEAD_IMPLEMENTER_TRUNCATION_STAGE,
    dead_implementer_condition_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.types import WorkItem

_UNCHANGED_TREE_STDERR = (
    "LIVESPEC_DEAD_IMPLEMENTER: unchanged tree after implementer; "
    "no janitor/review/disposition rounds will run against dispatch base"
)
_CHECK_FAILED_STDERR = (
    "LIVESPEC_DEAD_IMPLEMENTER_CHECK_FAILED: git diff against origin/master...HEAD "
    "failed; fail closed before review"
)
_ORDINARY_FAILURE_STDERR = "node `janitor` failed: just check exited 1"


def test_unchanged_tree_sentinel_names_its_own_governing_condition() -> None:
    condition = dead_implementer_condition_from_text(text=_UNCHANGED_TREE_STDERR)

    assert condition == "dead_implementer_unchanged_tree"


def test_unprovable_diff_is_named_apart_from_a_proven_unchanged_tree() -> None:
    """The check-failed sentinel has the plain one as its PREFIX, so order matters.

    Both arms reach the same terminal node, but they are different facts: one is
    a measured absence of work, the other is a refusal to guess when the diff
    command itself failed. Reporting the second as the first would claim a
    measurement nobody took.
    """
    condition = dead_implementer_condition_from_text(text=_CHECK_FAILED_STDERR)

    assert condition == "dead_implementer_diff_unprovable"


def test_ordinary_failure_text_carries_no_governing_condition() -> None:
    condition = dead_implementer_condition_from_text(text=_ORDINARY_FAILURE_STDERR)

    assert condition is None


def test_dead_implementer_truncation_journals_the_id_and_governing_condition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _journal(tmp_path=tmp_path)
    _stub_unrelated_dispositions(monkeypatch=monkeypatch)

    _run_dispositions(
        tmp_path=tmp_path,
        journal=journal,
        stderr=_UNCHANGED_TREE_STDERR,
    )

    records = _records(journal=journal)
    truncations = [
        record for record in records if record["stage"] == DEAD_IMPLEMENTER_TRUNCATION_STAGE
    ]
    assert [_payload(record=record) for record in truncations] == [
        {
            "stage": DEAD_IMPLEMENTER_TRUNCATION_STAGE,
            "work_item_id": "bd-ib-8nnu",
            "governing_condition": "dead_implementer_unchanged_tree",
            "fabro_run_id": "01RUNDEAD",
        }
    ]


def test_truncation_record_is_distinguishable_from_the_ordinary_failure_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncation and an ordinary implementer failure share status and stage.

    Both are `failed` at the `fabro-run` stage, so the generic outcome record
    cannot separate them; the truncation's own stage is what does.
    """
    truncated_journal = _journal(tmp_path=tmp_path / "truncated")
    ordinary_journal = _journal(tmp_path=tmp_path / "ordinary")
    _stub_unrelated_dispositions(monkeypatch=monkeypatch)

    _run_dispositions(
        tmp_path=tmp_path,
        journal=truncated_journal,
        stderr=_UNCHANGED_TREE_STDERR,
    )
    _run_dispositions(
        tmp_path=tmp_path,
        journal=ordinary_journal,
        stderr=_ORDINARY_FAILURE_STDERR,
    )

    truncated = [record["stage"] for record in _records(journal=truncated_journal)]
    ordinary = [record["stage"] for record in _records(journal=ordinary_journal)]
    assert truncated == [DEAD_IMPLEMENTER_TRUNCATION_STAGE, "outcome"]
    assert ordinary == ["outcome"]


def test_run_whose_implementer_changed_the_worktree_writes_no_truncation_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The breaker only fires on an unchanged tree, so a changed one emits no sentinel."""
    journal = _journal(tmp_path=tmp_path)
    _stub_unrelated_dispositions(monkeypatch=monkeypatch)

    _run_dispositions(
        tmp_path=tmp_path,
        journal=journal,
        stderr=_ORDINARY_FAILURE_STDERR,
    )

    records = _records(journal=journal)
    assert [
        record for record in records if record["stage"] == DEAD_IMPLEMENTER_TRUNCATION_STAGE
    ] == []


def _run_dispositions(*, tmp_path: Path, journal: JournalFile, stderr: str) -> None:
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id="01RUNDEAD",
        inspect=None,
        exit_code=1,
        stderr=stderr,
    )
    assert outcome is not None
    _dispatcher_loop_selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=_item(),
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
    )


def _stub_unrelated_dispositions(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence the dispositions that are not this test's subject.

    Each of them touches the ledger or the forge; leaving them live would make
    the journal assertion depend on machinery this change does not own.
    """
    for name in (
        "preserve_checkpointed_work_reference",
        "escalate_needs_human_block",
        "bounce_non_convergence_to_backlog",
        "record_dispatch_runtime_convergence",
        "emit_calibration",
    ):
        monkeypatch.setattr(_dispatcher_loop_selection, name, lambda **_: None)


def _journal(*, tmp_path: Path) -> JournalFile:
    return JournalFile(path=tmp_path / "journal.jsonl")


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    text = journal.path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _payload(*, record: dict[str, object]) -> dict[str, object]:
    """Drop the append layer's stamped envelope, leaving the writer's payload."""
    stamped = ("at", "invoker", "invoker_source")
    return {key: value for key, value in record.items() if key not in stamped}


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-8nnu",
        branch="feat/bd-ib-8nnu",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-8nnu",
        type="task",
        status="active",
        title="A dispatched task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-08-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )

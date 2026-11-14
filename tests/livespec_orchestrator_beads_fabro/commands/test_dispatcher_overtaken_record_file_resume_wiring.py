"""The production wiring behind Scenario 184's automatic record-file resume."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_lifecycle_writes as writes
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop as loop_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection as selection
from livespec_orchestrator_beads_fabro.commands import _dispatcher_overtaken_resume as overtaken
from livespec_orchestrator_beads_fabro.commands import _dispatcher_resume_command as resume_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    MERGE_POLL_BUDGET_EXHAUSTED,
    BaseAdvancedAfterArming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_file_resume import (
    resume_overtaken_record_files,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_run import DispatchLaunchContext

_CONFIG = (
    '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"record_files":'
    '[{"path":"record.json"}]}}}'
)
_ITEM_ID = "bd-ib-mfl2qa"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _outcome(*, base_advanced: BaseAdvancedAfterArming | None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="blocked",
        stage="merge-poll",
        pr_number=184,
        merge_sha=None,
        detail="base advanced",
        fabro_run_id="01M6W31BSSE1P8Z43EGGY9XVNF",
        base_advanced=base_advanced,
    )


def _advanced(
    *,
    paths: tuple[str, ...] | None = ("record.json",),
    head: str | None = "head1111",
    tip: str | None = "base2222",
    cause: str = "base-advanced-after-arming",
) -> BaseAdvancedAfterArming:
    return BaseAdvancedAfterArming(
        factory="petri",
        pr_head=head,
        default_branch_tip=tip,
        conflicted_paths=paths,
        cause=cause,
    )


@pytest.mark.parametrize(
    "base_advanced",
    [
        None,
        _advanced(cause=MERGE_POLL_BUDGET_EXHAUSTED),
        _advanced(paths=None),
        _advanced(head=None),
        _advanced(tip=None),
        _advanced(paths=("record.json", "src/other.py")),
        _advanced(paths=()),
    ],
)
def test_an_ending_the_record_file_arm_does_not_admit_is_left_to_rest(
    base_advanced: BaseAdvancedAfterArming | None,
) -> None:
    journal = _Journal()
    never = Mock()

    result = resume_overtaken_record_files(
        outcome=_outcome(base_advanced=base_advanced),
        config_text=_CONFIG,
        journal=journal,
        resolve_ready=lambda **_: None,
        resume=never,
    )

    assert result is None
    assert journal.records == []
    never.assert_not_called()


def test_an_undeclared_repository_leaves_every_conflict_to_rest() -> None:
    never = Mock()
    result = resume_overtaken_record_files(
        outcome=_outcome(base_advanced=_advanced()),
        config_text="{}",
        journal=_Journal(),
        resolve_ready=lambda **_: None,
        resume=never,
    )

    assert result is None
    never.assert_not_called()


def test_the_admitted_ending_journals_the_measured_row_then_resolves_and_resumes() -> None:
    journal = _Journal()
    events: list[str] = []
    resumed = _outcome(base_advanced=None)

    def resolve_ready(*, work_item_id: str) -> None:
        events.append(f"ready:{work_item_id}")

    def resume(*, work_item_id: str) -> DispatchOutcome:
        events.append(f"resume:{work_item_id}")
        return resumed

    result = resume_overtaken_record_files(
        outcome=_outcome(base_advanced=_advanced()),
        config_text=_CONFIG,
        journal=journal,
        resolve_ready=resolve_ready,
        resume=resume,
    )

    assert result is resumed
    assert events == [f"ready:{_ITEM_ID}", f"resume:{_ITEM_ID}"]
    assert journal.records == [
        {
            "stage": "base-advanced-record-files-resume",
            "work_item_id": _ITEM_ID,
            "run_id": "01M6W31BSSE1P8Z43EGGY9XVNF",
            "pr_number": 184,
            "pr_head": "head1111",
            "default_branch_tip": "base2222",
            "conflicted_paths": ["record.json"],
        }
    ]


def test_a_dispatch_with_a_resume_seam_still_rests_an_ending_the_arm_does_not_admit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "record_provider_exhaustion_if_observed",
        "record_dead_implementer_truncation_if_observed",
        "preserve_terminated_run_work",
        "record_groom_draft",
        "record_base_advanced_after_arming",
        "escalate_needs_human_block",
        "record_needs_human_cause",
        "dispose_terminal_routing",
        "emit_calibration",
    ):
        monkeypatch.setattr(selection, name, lambda **_: None)
    monkeypatch.setattr(selection, "livespec_config_text", lambda **_: _CONFIG)
    outcome = _outcome(base_advanced=_advanced(paths=("src/other.py",)))
    journal: Any = SimpleNamespace(path=tmp_path / "journal.jsonl", append=lambda **_: None)
    never = Mock()

    result = selection.post_run_dispositions(
        args=argparse.Namespace(close_on_merge=False),
        repo=tmp_path,
        item=SimpleNamespace(id=_ITEM_ID),  # pyright: ignore[reportArgumentType]
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
        resume=never,
    )

    assert result is outcome
    never.assert_not_called()


def test_the_ready_release_journals_the_ended_runs_terminal_before_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _Journal()
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        selection,
        "write_blocked_state_and_reconcile",
        lambda **kwargs: seen.append({"rows": len(journal.records), **kwargs}),
    )

    selection._release_for_resume(  # noqa: SLF001 - the exact boundary under test.
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        outcome=_outcome(base_advanced=_advanced()),
        journal=journal,  # pyright: ignore[reportArgumentType]
    )

    assert journal.records[0]["stage"] == "outcome"
    assert seen == [
        {
            "rows": 1,
            "repo": tmp_path,
            "item_id": _ITEM_ID,
            "status": "ready",
            "blocked_reason": None,
        }
    ]


def test_the_blocked_state_write_resolves_the_store_from_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = object()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(writes, "store_config", lambda **_: store)
    monkeypatch.setattr(
        writes,
        "update_work_item_blocked_state",
        lambda *, path, **_: calls.append(("write", path)),
    )
    monkeypatch.setattr(
        writes,
        "reconcile_after_lifecycle_write",
        lambda *, path, **_: calls.append(("reconcile", path)),
    )

    writes.write_blocked_state_and_reconcile(
        repo=tmp_path, item_id=_ITEM_ID, status="ready", blocked_reason=None
    )

    assert calls == [("write", store), ("reconcile", store)]


def test_a_dispatch_hands_its_launch_resume_to_its_locked_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []
    outcome = _outcome(base_advanced=None)

    def locked(**kwargs: Any) -> DispatchOutcome:
        seen.append(kwargs["lifetime"].resume)
        return outcome

    monkeypatch.setattr(loop_module, "_dispatch_one_locked", locked)
    monkeypatch.setattr(loop_module, "release_pre_run_claim_if_needed", lambda **_: None)

    offered = Mock()

    result = loop_module.dispatch_one(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=SimpleNamespace(id=_ITEM_ID),  # pyright: ignore[reportArgumentType]
        journal=_Journal(),  # pyright: ignore[reportArgumentType]
        launch=DispatchLaunchContext(resume=offered),
    )

    assert result is outcome
    assert seen == [offered]


@dataclass(kw_only=True)
class _ResumeWorld:
    """What the resume command's collaborators report, so each arm can be driven."""

    refusals: tuple[str, ...] = ()
    anchored: bool = True
    events: list[str] = field(default_factory=list)


def _install(
    *, monkeypatch: pytest.MonkeyPatch, world: _ResumeWorld
) -> tuple[DispatchOutcome, Callable[..., DispatchOutcome]]:
    dispatched = _outcome(base_advanced=None)
    item = SimpleNamespace(id=_ITEM_ID)
    gather = SimpleNamespace(
        anchor=(
            SimpleNamespace(head="head1111", resumed_at="pr_refresh", source="proof-record")
            if world.anchored
            else None
        ),
        observation=SimpleNamespace(pull_request=184),
        earlier_run_ids=("01M6W31BSSE1P8Z43EGGY9XVNF",),
        workflow_name=None,
    )
    monkeypatch.setattr(overtaken, "load_items", lambda **_: [item])
    monkeypatch.setattr(overtaken, "gather_resume", lambda **_: gather)
    monkeypatch.setattr(overtaken, "resume_refusals", lambda **_: world.refusals)
    monkeypatch.setattr(
        overtaken,
        "write_blocked_state_and_reconcile",
        lambda **kwargs: world.events.append(f"write:{kwargs['status']}"),
    )

    def admit(**kwargs: Any) -> DispatchOutcome:
        world.events.append(f"admit:{kwargs['args'].resume_head}")
        return dispatched

    return dispatched, admit


def test_the_offered_resume_is_the_resume_command_path_for_the_named_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _ResumeWorld()
    dispatched, admit = _install(monkeypatch=monkeypatch, world=world)
    journal = _Journal()

    resume = overtaken.bound_overtaken_resume(
        args=argparse.Namespace(journal=None),
        repo=tmp_path,
        journal=journal,  # pyright: ignore[reportArgumentType]
        janitor=None,
        admit_and_dispatch=admit,
    )
    result = resume(work_item_id=_ITEM_ID)

    assert result is dispatched
    assert world.events == ["admit:head1111"]
    assert journal.records[0]["stage"] == "resume"
    assert journal.records[0]["work_item_id"] == _ITEM_ID


@pytest.mark.parametrize(
    ("refusals", "anchored"),
    [(("the pull request is closed",), True), ((), False)],
)
def test_a_refused_resume_rests_the_item_at_needs_human_and_names_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, refusals: tuple[str, ...], anchored: bool
) -> None:
    world = _ResumeWorld(refusals=refusals, anchored=anchored)
    _, admit = _install(monkeypatch=monkeypatch, world=world)
    journal = _Journal()

    result = overtaken.bound_overtaken_resume(
        args=argparse.Namespace(journal=None),
        repo=tmp_path,
        journal=journal,  # pyright: ignore[reportArgumentType]
        janitor=None,
        admit_and_dispatch=admit,
    )(work_item_id=_ITEM_ID)

    assert world.events == ["write:blocked"]
    assert result.status == "blocked"
    assert result.stage == "merge-poll"
    assert result.pr_number == 184
    assert result.detail.startswith("base-advanced-after-arming: the automatic resume")
    assert (refusals[0] if refusals else "nothing to resume from") in result.detail
    assert journal.records[0]["stage"] == "needs-human-blocked"


def test_the_command_offers_its_own_launch_as_the_admit_and_dispatch_path() -> None:
    assert resume_module.overtaken_resume.func is overtaken.bound_overtaken_resume
    assert resume_module.overtaken_resume.keywords == {
        "admit_and_dispatch": resume_module._admit_and_dispatch_resume  # noqa: SLF001
    }

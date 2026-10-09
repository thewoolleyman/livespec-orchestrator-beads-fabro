"""Scenario 153: adopted assertion ceilings and attributed exceptions.

This integration journey binds the size gate through the same shared decision
that capture, groom, approval, and factory dispatch consume.  Store-facing
cases use the real in-memory beads seam; only processes outside the repository
are stood in.
"""

from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GroomDoorRefusal,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    GroomApproval,
    file_approved_slices,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io


def _item(*, assertion_count: int, item_id: str = "bd-size") -> WorkItem:
    bullets = "\n".join(
        f"- The product satisfies assertion {index}." for index in range(assertion_count)
    )
    return WorkItem(
        id=item_id,
        type="feature",
        status="ready",
        title="Factory size gate",
        description=(
            "## Definition of Done\n\n"
            f"{bullets}\n\n"
            "References: ## Scenario 153 — An adopted assertion ceiling requires "
            "an attributed exception without waiving other gates\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _size_gate_module() -> Any:
    return import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate")


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


def _ready_checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def _seed_capture(*, config: StoreConfig, item_id: str, assertion_count: int = 1) -> None:
    client = make_beads_client(config=config)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="feature",
            title="Factory size gate",
            description=_item(assertion_count=assertion_count, item_id=item_id).description,
            priority=2,
            assignee=None,
            created_at="2026-10-09T00:00:00Z",
            labels=["admission:auto"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=item_id, status="backlog")


def _write_repo_config(*, repo: Path, ceiling: int, groom_variant: str | None = None) -> None:
    dispatcher: dict[str, object] = {"adopted_assertion_count_ceiling": ceiling}
    if groom_variant is not None:
        relative = f".fabro/workflows/{groom_variant}"
        workflow = repo / relative
        workflow.mkdir(parents=True)
        (workflow / "workflow.toml").write_text(
            '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
            encoding="utf-8",
        )
        dispatcher["workflows"] = {groom_variant: relative}
    (repo / ".livespec.jsonc").write_text(
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
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )


def _stored(*, config: StoreConfig) -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=config))


def _size_reason_for(*, config: StoreConfig, item_id: str) -> str:
    comments = make_beads_client(config=config).list_comments(issue_id=item_id)
    matches = [
        comment["text"]
        for comment in comments
        if isinstance(comment.get("text"), str) and "size_justification" in comment["text"]
    ]
    assert len(matches) == 1
    return cast("str", matches[0])


def _assert_missing_reason(*, reason: str, assertion_count: int = 3) -> None:
    assert "adopted assertion-count ceiling 2" in reason
    assert f"sanctioned-parser assertion count {assertion_count}" in reason
    assert "missing or invalid size_justification" in reason


def test_absent_ceiling_leaves_every_entry_path_on_ordinary_admission() -> None:
    """No adopted ceiling means justification presence has no gate effect."""
    module = _size_gate_module()
    valid = {
        "rationale": "This slice is cohesive despite its assertion count.",
        "author": "human:maintainer",
        "at": "2026-10-09T00:00:00Z",
    }

    decisions = [
        cast(
            "Any",
            module.factory_size_decision(
                item=_item(assertion_count=4, item_id=f"bd-{surface}-{variant}"),
                adopted_ceiling=None,
                raw_justification=raw,
            ),
        )
        for surface in ("capture", "groom", "approval", "dispatch")
        for variant, raw in (("missing", None), ("present", valid))
    ]

    assert [decision.disposition for decision in decisions] == ["proceed"] * 8
    assert all(decision.adopted_ceiling is None for decision in decisions)
    assert all(decision.assertion_count == 4 for decision in decisions)
    assert all(decision.reason is None for decision in decisions)
    assert all(decision.size_justified is False for decision in decisions)


def test_invalid_adopted_ceiling_refuses_before_lifecycle_mutation(tmp_path: Path) -> None:
    """Every non-positive or non-integer configured value fails closed."""
    invalid_values: tuple[object, ...] = (0, -1, True, False, 1.5, "3")

    for index, value in enumerate(invalid_values):
        reset_fake_singleton()
        repo = tmp_path / str(index)
        repo.mkdir()
        (repo / ".livespec.jsonc").write_text(
            json.dumps(
                {
                    "livespec-orchestrator-beads-fabro": {
                        "dispatcher": {"adopted_assertion_count_ceiling": value}
                    }
                }
            ),
            encoding="utf-8",
        )
        config = _config(repo_root=repo)
        item_id = f"bd-invalid-{index}"
        _seed_capture(config=config, item_id=item_id)

        result = apply_intake_dor(
            path=config,
            item_id=item_id,
            checklist=_ready_checklist(),
        )

        assert not is_successful(result)
        failure = unsafe_perform_io(result.failure())
        assert failure.setting == "adopted_assertion_count_ceiling"
        assert "positive integer" in failure.detail
        assert make_beads_client(config=config).show_issue(issue_id=item_id)["status"] == "backlog"

    manifest_keys = {
        entry["key"]
        for entry in cast("list[dict[str, object]]", api_configurable_key_manifest()["keys"])
    }
    assert "adopted_assertion_count_ceiling" not in manifest_keys


def _exercise_unjustified_capture(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    capture_repo = tmp_path / "capture"
    capture_repo.mkdir()
    _write_repo_config(repo=capture_repo, ceiling=2)
    capture_config = _config(repo_root=capture_repo)
    _seed_capture(config=capture_config, item_id="bd-capture", assertion_count=3)
    capture_result = apply_intake_dor(
        path=capture_config,
        item_id="bd-capture",
        checklist=_ready_checklist(),
    )
    assert is_successful(capture_result)
    assert unsafe_perform_io(capture_result.unwrap()) == "backlog"
    assert _stored(config=capture_config)["bd-capture"].status == "backlog"
    _assert_missing_reason(reason=_size_reason_for(config=capture_config, item_id="bd-capture"))


def _exercise_unjustified_groom(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    groom_repo = tmp_path / "groom"
    groom_repo.mkdir()
    _write_repo_config(repo=groom_repo, ceiling=2)
    groom_config = _config(repo_root=groom_repo)
    epic = replace(
        _item(assertion_count=1, item_id="bd-epic"),
        type="epic",
        status="backlog",
    )
    append_work_item(path=groom_config, item=epic)
    groomed = file_approved_slices(
        path=groom_config,
        regroom_item_id=epic.id,
        local_repo=groom_repo.name,
        approval=GroomApproval(approver="human:maintainer", route="approval comment"),
        slices=[
            CandidateSlice(
                title="Oversized replacement",
                description=_item(assertion_count=3).description,
                acceptance="The replacement is verified.",
                autonomy_tier="factory",
                repo_target=groom_repo.name,
            )
        ],
    )
    groomed_id = groomed.filed_slice_ids[0]
    assert _stored(config=groom_config)[groomed_id].status == "backlog"
    _assert_missing_reason(
        reason=_size_reason_for(config=groom_config, item_id=groomed_id),
        assertion_count=5,
    )


def _exercise_unjustified_approval(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    approval_repo = tmp_path / "approval"
    approval_repo.mkdir()
    _write_repo_config(repo=approval_repo, ceiling=2)
    approval_config = _config(repo_root=approval_repo)
    approval_item = replace(
        _item(assertion_count=3, item_id="bd-approval"),
        status="pending-approval",
        admission_policy="manual",
    )
    append_work_item(path=approval_config, item=approval_item)
    approval = run_action(repo=approval_repo, action_id="approve:bd-approval")
    assert approval["status"] == "failed"
    assert approval["target_status"] == "backlog"
    _assert_missing_reason(reason=cast("str", approval["message"]))
    assert _stored(config=approval_config)[approval_item.id].status == "backlog"


def _exercise_unjustified_dispatch(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    dispatch_repo = tmp_path / "dispatch"
    dispatch_repo.mkdir()
    _write_repo_config(repo=dispatch_repo, ceiling=2)
    dispatch_config = _config(repo_root=dispatch_repo)
    dispatch_item = _item(assertion_count=3, item_id="bd-dispatch")
    append_work_item(path=dispatch_config, item=dispatch_item)
    admission = admit_and_select(
        repo=dispatch_repo,
        items=[dispatch_item],
        candidates=[dispatch_item],
        journal=JournalFile(path=dispatch_repo / "journal.jsonl"),
        enforce_cap=False,
    )
    assert admission.admitted == []
    assert len(admission.refused) == 1
    _assert_missing_reason(reason=admission.refused[0].detail or "")
    assert _stored(config=dispatch_config)[dispatch_item.id].status == "backlog"


def _exercise_unjustified_groom_door(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    door_repo = tmp_path / "groom-door"
    door_repo.mkdir()
    _write_repo_config(repo=door_repo, ceiling=2, groom_variant="groom-cut")
    door_config = _config(repo_root=door_repo)
    door_item = replace(_item(assertion_count=3, item_id="bd-groom-door"), status="backlog")
    append_work_item(path=door_config, item=door_item)
    door = groom_dispatch(
        repo=door_repo,
        item=door_item,
        variant="groom-cut",
        journal=JournalFile(path=door_repo / "journal.jsonl"),
    )
    assert isinstance(door, GroomDoorRefusal)
    assert door.cause == "size-decomposition"
    _assert_missing_reason(reason=door.detail)
    assert _stored(config=door_config)[door_item.id].status == "backlog"


def test_above_ceiling_without_justification_routes_every_public_gate_to_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capture, groom, approval, and both dispatch doors share one refusal."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    _exercise_unjustified_capture(tmp_path=tmp_path)
    _exercise_unjustified_groom(tmp_path=tmp_path)
    _exercise_unjustified_approval(tmp_path=tmp_path)
    _exercise_unjustified_dispatch(tmp_path=tmp_path)
    _exercise_unjustified_groom_door(tmp_path=tmp_path)

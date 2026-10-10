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
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_span import (
    calibration_request_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GroomDoorRefusal,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import (
    TddOrderSink,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import (
    gather_tdd_signals,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    GroomApproval,
    file_approved_slices,
)
from livespec_orchestrator_beads_fabro.errors import GroomDraftError
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


def _write_repo_config(
    *,
    repo: Path,
    ceiling: int | None,
    groom_variant: str | None = None,
    groom_cut_approval: str | None = None,
) -> None:
    dispatcher: dict[str, object] = {}
    if ceiling is not None:
        dispatcher["adopted_assertion_count_ceiling"] = ceiling
    if groom_cut_approval is not None:
        dispatcher["groom_cut_approval"] = groom_cut_approval
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


def _record_size_justification(*, config: StoreConfig, item_id: str, justification: object) -> None:
    client = make_beads_client(config=config)
    record = client.show_issue(issue_id=item_id)
    raw_metadata = record.get("metadata")
    metadata = (
        dict(cast("dict[str, object]", raw_metadata)) if isinstance(raw_metadata, dict) else {}
    )
    metadata["size_justification"] = justification
    client.update_issue(issue_id=item_id, metadata=metadata)


def _write_scenario_reference(*, repo: Path) -> None:
    spec = repo / "SPECIFICATION"
    spec.mkdir()
    (spec / "scenarios.md").write_text(
        "## Scenario 153 — An adopted assertion ceiling requires an attributed exception "
        "without waiving other gates\n",
        encoding="utf-8",
    )


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

    _exercise_invalid_public_entries(tmp_path=tmp_path)


def _exercise_invalid_public_entries(*, tmp_path: Path) -> None:
    reset_fake_singleton()
    repo = tmp_path / "public-entries"
    repo.mkdir()
    _write_repo_config(repo=repo, ceiling=0, groom_variant="groom-cut")
    _write_scenario_reference(repo=repo)
    config = _config(repo_root=repo)
    _exercise_invalid_approval(repo=repo, config=config)
    _exercise_invalid_dispatch(repo=repo, config=config)
    _exercise_invalid_groom_door(repo=repo, config=config)
    _exercise_invalid_groom_filing(repo=repo, config=config)


def _exercise_invalid_approval(*, repo: Path, config: StoreConfig) -> None:
    approval_item = replace(
        _item(assertion_count=3, item_id="bd-invalid-approval"),
        status="pending-approval",
        admission_policy="manual",
    )
    append_work_item(path=config, item=approval_item)
    approval = run_action(repo=repo, action_id=f"approve:{approval_item.id}")
    assert approval["domain_error"] == "policy-setting-unreadable"
    assert "positive integer" in cast("str", approval["summary"])
    assert _stored(config=config)[approval_item.id].status == "pending-approval"


def _exercise_invalid_dispatch(*, repo: Path, config: StoreConfig) -> None:
    dispatch_item = _item(assertion_count=3, item_id="bd-invalid-dispatch")
    append_work_item(path=config, item=dispatch_item)
    admission = admit_and_select(
        repo=repo,
        items=[dispatch_item],
        candidates=[dispatch_item],
        journal=JournalFile(path=repo / "invalid-dispatch.jsonl"),
        enforce_cap=False,
    )
    assert admission.admitted == []
    assert admission.refused[0].stage == "configuration"
    assert "positive integer" in (admission.refused[0].detail or "")
    assert _stored(config=config)[dispatch_item.id].status == "ready"


def _exercise_invalid_groom_door(*, repo: Path, config: StoreConfig) -> None:
    door_item = replace(_item(assertion_count=3, item_id="bd-invalid-door"), status="backlog")
    append_work_item(path=config, item=door_item)
    door = groom_dispatch(
        repo=repo,
        item=door_item,
        variant="groom-cut",
        journal=JournalFile(path=repo / "invalid-groom-door.jsonl"),
    )
    assert isinstance(door, GroomDoorRefusal)
    assert door.cause == "configuration"
    assert "positive integer" in door.detail
    assert _stored(config=config)[door_item.id].status == "backlog"


def _exercise_invalid_groom_filing(*, repo: Path, config: StoreConfig) -> None:
    epic = replace(
        _item(assertion_count=1, item_id="bd-invalid-epic"), type="epic", status="backlog"
    )
    append_work_item(path=config, item=epic)
    ids_before = set(_stored(config=config))
    with pytest.raises(GroomDraftError, match="positive integer"):
        file_approved_slices(
            path=config,
            regroom_item_id=epic.id,
            local_repo=repo.name,
            approval=GroomApproval(approver="human:maintainer", route="approval comment"),
            slices=[
                CandidateSlice(
                    title="Invalid configuration slice",
                    description=_item(assertion_count=3).description,
                    acceptance="The replacement is verified.",
                    autonomy_tier="factory",
                    repo_target=repo.name,
                )
            ],
        )
    assert set(_stored(config=config)) == ids_before
    assert _stored(config=config)[epic.id].status == "backlog"


def _exercise_unjustified_capture(*, tmp_path: Path, justification: object = None) -> None:
    reset_fake_singleton()
    capture_repo = tmp_path / "capture"
    capture_repo.mkdir()
    _write_repo_config(repo=capture_repo, ceiling=2)
    capture_config = _config(repo_root=capture_repo)
    _seed_capture(config=capture_config, item_id="bd-capture", assertion_count=3)
    if justification is not None:
        _record_size_justification(
            config=capture_config,
            item_id="bd-capture",
            justification=justification,
        )
    capture_result = apply_intake_dor(
        path=capture_config,
        item_id="bd-capture",
        checklist=_ready_checklist(),
    )
    assert is_successful(capture_result)
    assert unsafe_perform_io(capture_result.unwrap()) == "backlog"
    assert _stored(config=capture_config)["bd-capture"].status == "backlog"
    _assert_missing_reason(reason=_size_reason_for(config=capture_config, item_id="bd-capture"))


def _exercise_unjustified_groom(*, tmp_path: Path, justification: object = None) -> None:
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
                size_justification=justification,
            )
        ],
    )
    groomed_id = groomed.filed_slice_ids[0]
    assert _stored(config=groom_config)[groomed_id].status == "backlog"
    _assert_missing_reason(
        reason=_size_reason_for(config=groom_config, item_id=groomed_id),
        assertion_count=5,
    )


def _exercise_unjustified_approval(*, tmp_path: Path, justification: object = None) -> None:
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
    if justification is not None:
        _record_size_justification(
            config=approval_config,
            item_id=approval_item.id,
            justification=justification,
        )
    approval = run_action(repo=approval_repo, action_id="approve:bd-approval")
    assert approval["status"] == "failed"
    assert approval["target_status"] == "backlog"
    _assert_missing_reason(reason=cast("str", approval["message"]))
    assert _stored(config=approval_config)[approval_item.id].status == "backlog"


def _exercise_unjustified_dispatch(*, tmp_path: Path, justification: object = None) -> None:
    reset_fake_singleton()
    dispatch_repo = tmp_path / "dispatch"
    dispatch_repo.mkdir()
    _write_repo_config(repo=dispatch_repo, ceiling=2)
    dispatch_config = _config(repo_root=dispatch_repo)
    dispatch_item = _item(assertion_count=3, item_id="bd-dispatch")
    append_work_item(path=dispatch_config, item=dispatch_item)
    if justification is not None:
        _record_size_justification(
            config=dispatch_config,
            item_id=dispatch_item.id,
            justification=justification,
        )
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


def _exercise_unjustified_groom_door(*, tmp_path: Path, justification: object = None) -> None:
    reset_fake_singleton()
    door_repo = tmp_path / "groom-door"
    door_repo.mkdir()
    _write_repo_config(repo=door_repo, ceiling=2, groom_variant="groom-cut")
    door_config = _config(repo_root=door_repo)
    door_item = replace(_item(assertion_count=3, item_id="bd-groom-door"), status="backlog")
    append_work_item(path=door_config, item=door_item)
    if justification is not None:
        _record_size_justification(
            config=door_config,
            item_id=door_item.id,
            justification=justification,
        )
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


def test_malformed_size_justifications_never_waive_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the exact attributed and timestamped object is an exception."""
    valid = _valid_justification()
    malformed: tuple[object, ...] = (
        None,
        [],
        {},
        {"rationale": valid["rationale"], "author": valid["author"]},
        valid | {"unexpected": "not sanctioned"},
        valid | {"rationale": 1},
        valid | {"author": False},
        valid | {"at": []},
        valid | {"rationale": "  "},
        valid | {"author": "\t"},
        valid | {"at": ""},
        valid | {"at": "not-a-timestamp"},
    )
    decisions = [
        cast(
            "Any",
            _size_gate_module().factory_size_decision(
                item=_item(assertion_count=3, item_id=f"bd-malformed-{index}"),
                adopted_ceiling=2,
                raw_justification=raw,
            ),
        )
        for index, raw in enumerate(malformed)
    ]
    assert all(decision.disposition == "decompose" for decision in decisions)
    assert all(decision.size_justified is False for decision in decisions)

    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    invalid_timestamp = valid | {"at": "not-a-timestamp"}
    journey = tmp_path / "malformed-public-entries"
    journey.mkdir()
    _exercise_unjustified_capture(tmp_path=journey, justification=invalid_timestamp)
    _exercise_unjustified_groom(tmp_path=journey, justification=invalid_timestamp)
    _exercise_unjustified_approval(tmp_path=journey, justification=invalid_timestamp)
    _exercise_unjustified_dispatch(tmp_path=journey, justification=invalid_timestamp)
    _exercise_unjustified_groom_door(tmp_path=journey, justification=invalid_timestamp)


def test_items_at_or_below_ceiling_continue_through_ordinary_gates() -> None:
    """The adopted ceiling is inclusive and adds no justification duty below it."""
    module = _size_gate_module()

    decisions = [
        cast(
            "Any",
            module.factory_size_decision(
                item=_item(assertion_count=count, item_id=f"bd-{surface}-{count}"),
                adopted_ceiling=2,
                raw_justification=None,
            ),
        )
        for surface in ("capture", "groom", "approval", "dispatch")
        for count in (1, 2)
    ]

    assert [decision.disposition for decision in decisions] == ["proceed"] * 8
    assert [decision.assertion_count for decision in decisions] == [1, 2] * 4
    assert all(decision.reason is None for decision in decisions)
    assert all(decision.size_justified is False for decision in decisions)


def _valid_justification() -> dict[str, str]:
    return {
        "rationale": "This larger slice preserves one coherent transactional change.",
        "author": "human:maintainer",
        "at": "2026-10-09T00:00:00Z",
    }


def _assert_valid_size_decision(*, valid: dict[str, str]) -> None:
    decision = cast(
        "Any",
        _size_gate_module().factory_size_decision(
            item=_item(assertion_count=3, item_id="bd-decision"),
            adopted_ceiling=2,
            raw_justification=valid,
        ),
    )
    assert decision.disposition == "proceed"
    assert decision.size_justified is True


def _exercise_valid_capture_dispatch_and_telemetry(
    *, repo: Path, config: StoreConfig, valid: dict[str, str]
) -> None:
    _seed_capture(config=config, item_id="bd-capture-valid", assertion_count=3)
    _record_size_justification(
        config=config,
        item_id="bd-capture-valid",
        justification=valid,
    )
    captured = apply_intake_dor(
        path=config,
        item_id="bd-capture-valid",
        checklist=_ready_checklist(),
    )
    assert is_successful(captured)
    assert unsafe_perform_io(captured.unwrap()) == "ready"

    captured_item = _stored(config=config)["bd-capture-valid"]
    admission = admit_and_select(
        repo=repo,
        items=[captured_item],
        candidates=[captured_item],
        journal=JournalFile(path=repo / "journal.jsonl"),
        enforce_cap=False,
    )
    assert [item.id for item in admission.admitted] == [captured_item.id]
    signals = gather_tdd_signals(
        repo=repo,
        item=captured_item,
        outcome=DispatchOutcome(
            work_item_id=captured_item.id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha="abc123",
            detail="merged",
        ),
        records=(),
        sink=TddOrderSink(path=repo / "tdd-order.json"),
        runner=cast("Any", object()),
    )
    record = build_calibration_record(
        item=captured_item,
        outcome=DispatchOutcome(
            work_item_id=captured_item.id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha="abc123",
            detail="merged",
        ),
        repo_name=repo.name,
        journal_records=(),
        wall_clock_seconds=1.0,
        token_cost_micros=None,
        dispatch_context_size=1,
        merged_pr_diff_size=None,
        tdd=signals,
    )
    payload = json.loads(calibration_request_line(record=record, now_ns=1))
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = {entry["key"]: entry["value"] for entry in span["attributes"]}
    assert attributes["tdd.size_justified"] == {"boolValue": True}


def _assert_valid_exception_preserves_ordinary_approval_gate(
    *, repo: Path, config: StoreConfig, valid: dict[str, str]
) -> None:
    refused_item = replace(
        _item(assertion_count=3, item_id="bd-ordinary-refusal"),
        status="pending-approval",
        admission_policy="manual",
        description="## Definition of Done\n\n- An unreferenced assertion remains.\n",
    )
    append_work_item(path=config, item=refused_item)
    _record_size_justification(
        config=config,
        item_id=refused_item.id,
        justification=valid,
    )
    approval = run_action(repo=repo, action_id=f"approve:{refused_item.id}")
    assert approval["domain_error"] == "ungradeable-acceptance-criteria"
    assert _stored(config=config)[refused_item.id].status == "pending-approval"


def _exercise_valid_groom_paths(*, repo: Path, config: StoreConfig, valid: dict[str, str]) -> None:
    epic = replace(_item(assertion_count=1, item_id="bd-valid-epic"), type="epic", status="backlog")
    append_work_item(path=config, item=epic)
    groomed = file_approved_slices(
        path=config,
        regroom_item_id=epic.id,
        local_repo=repo.name,
        approval=GroomApproval(approver="human:maintainer", route="approval comment"),
        slices=[
            CandidateSlice(
                title="Justified replacement",
                description=_item(assertion_count=3).description,
                acceptance="The replacement is verified.",
                autonomy_tier="factory",
                repo_target=repo.name,
                size_justification=valid,
            )
        ],
    )
    assert _stored(config=config)[groomed.filed_slice_ids[0]].status == "ready"

    door_item = replace(_item(assertion_count=3, item_id="bd-valid-door"), status="backlog")
    append_work_item(path=config, item=door_item)
    _record_size_justification(config=config, item_id=door_item.id, justification=valid)
    door = groom_dispatch(
        repo=repo,
        item=door_item,
        variant="groom-cut",
        journal=JournalFile(path=repo / "groom-journal.jsonl"),
    )
    assert not isinstance(door, GroomDoorRefusal)


def test_valid_exception_waives_only_size_and_marks_successful_dispatch_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An attributed exception survives every public gate but no ordinary one."""
    valid = _valid_justification()
    _assert_valid_size_decision(valid=valid)

    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "valid"
    repo.mkdir()
    _write_repo_config(repo=repo, ceiling=2, groom_variant="groom-cut")
    _write_scenario_reference(repo=repo)
    config = _config(repo_root=repo)

    _exercise_valid_capture_dispatch_and_telemetry(repo=repo, config=config, valid=valid)
    _assert_valid_exception_preserves_ordinary_approval_gate(
        repo=repo,
        config=config,
        valid=valid,
    )
    _exercise_valid_groom_paths(repo=repo, config=config, valid=valid)


def _consensus_cut_fixture(
    *, tmp_path: Path, name: str, ceiling: int | None
) -> tuple[Path, StoreConfig, WorkItem, CandidateSlice]:
    reset_fake_singleton()
    repo = tmp_path / name
    repo.mkdir()
    _write_repo_config(
        repo=repo,
        ceiling=ceiling,
        groom_cut_approval="consensus",
    )
    config = _config(repo_root=repo)
    epic = replace(
        _item(assertion_count=1, item_id=f"bd-consensus-{name}"),
        type="epic",
        status="backlog",
    )
    append_work_item(path=config, item=epic)
    candidate = CandidateSlice(
        title="Consensus replacement",
        description=_item(assertion_count=3).description,
        acceptance="The replacement is verified.",
        autonomy_tier="factory",
        repo_target=repo.name,
        size_justification=_valid_justification(),
    )
    return repo, config, epic, candidate


def test_consensus_first_cut_requires_an_adopted_ceiling_and_has_no_size_exception(
    tmp_path: Path,
) -> None:
    """The tier cannot approve without a ceiling or waive one with attribution."""
    absent_repo, absent_config, absent_epic, absent_candidate = _consensus_cut_fixture(
        tmp_path=tmp_path,
        name="absent",
        ceiling=None,
    )
    absent_ids = set(_stored(config=absent_config))
    with pytest.raises(GroomDraftError, match="consensus approval requires an adopted"):
        file_approved_slices(
            path=absent_config,
            regroom_item_id=absent_epic.id,
            local_repo=absent_repo.name,
            approval=GroomApproval(
                approver="consensus:ratified-tier",
                route="consensus first-cut approval",
            ),
            slices=[absent_candidate],
        )
    assert set(_stored(config=absent_config)) == absent_ids

    above_repo, above_config, above_epic, above_candidate = _consensus_cut_fixture(
        tmp_path=tmp_path,
        name="above",
        ceiling=4,
    )
    above_ids = set(_stored(config=above_config))
    with pytest.raises(GroomDraftError, match="size_justification cannot waive"):
        file_approved_slices(
            path=above_config,
            regroom_item_id=above_epic.id,
            local_repo=above_repo.name,
            approval=GroomApproval(
                approver="consensus:ratified-tier",
                route="consensus first-cut approval",
            ),
            slices=[above_candidate],
        )
    assert set(_stored(config=above_config)) == above_ids

    boundary_repo, boundary_config, boundary_epic, boundary_candidate = _consensus_cut_fixture(
        tmp_path=tmp_path,
        name="boundary",
        ceiling=5,
    )
    filed = file_approved_slices(
        path=boundary_config,
        regroom_item_id=boundary_epic.id,
        local_repo=boundary_repo.name,
        approval=GroomApproval(
            approver="consensus:ratified-tier",
            route="consensus first-cut approval",
        ),
        slices=[boundary_candidate],
    )
    assert _stored(config=boundary_config)[filed.filed_slice_ids[0]].status == "ready"

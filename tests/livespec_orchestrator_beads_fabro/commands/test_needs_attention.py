"""Tests for the needs-attention thin binding."""

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro._store_merge_hold import update_work_item_merge_hold
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    build_attention,
    main,
    render_json,
    render_markdown,
)
from livespec_orchestrator_beads_fabro.commands.plan import NextAction, append_handoff
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _set_ready_since(*, id_: str, ready_since: object) -> None:
    client = make_beads_client(config=_config())
    record = client.show_issue(issue_id=id_)
    metadata = dict(record.get("metadata")) if isinstance(record.get("metadata"), dict) else {}
    metadata["ready_since"] = ready_since
    client.update_issue(issue_id=id_, metadata=metadata)


def _seed_raw(
    *,
    id_: str,
    status: str,
    priority: int,
    labels: list[str] | None = None,
    title: str | None = None,
) -> None:
    """Seed an issue straight through the client seam — the raw `bd create` path.

    `append_work_item` is the capture front-ends' filing path; an agent or
    script that files with a bare `bd create` bypasses it, so the intake
    Definition-of-Ready gate never runs and the record lands WITHOUT the
    `intake:triaged` marker. That is exactly the population the un-triaged
    backlog lane must surface, so these cases seed it the way it really
    arrives. `priority` is the beads-native column (lower = more urgent),
    which `append_work_item` always writes as the neutral default.
    """
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=id_,
            issue_type="task",
            title=title if title is not None else f"{id_} title",
            description="d",
            priority=priority,
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
            labels=list(labels) if labels is not None else [],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id=id_, status=status)


def _write_config(
    project_root: Path,
    *,
    auto_approve_ready: bool = False,
    wip_cap: int | None = None,
    ready_aging_threshold_hours: int | None = None,
) -> None:
    dispatcher_items = []
    if auto_approve_ready:
        dispatcher_items.append(f'      "auto_approve_ready": {str(auto_approve_ready).lower()}')
    if wip_cap is not None:
        dispatcher_items.append(f'      "wip_cap": {wip_cap}')
    if ready_aging_threshold_hours is not None:
        dispatcher_items.append(
            f'      "ready_aging_threshold_hours": {ready_aging_threshold_hours}'
        )
    dispatcher_body = ",\n".join(dispatcher_items)
    dispatcher = (
        f""",
    \"dispatcher\": {{
{dispatcher_body}
    }}"""
        if dispatcher_items
        else ""
    )
    (project_root / ".livespec.jsonc").write_text(
        """{
  \"livespec-orchestrator-beads-fabro\": {
    \"connection\": {
      \"tenant\": \"livespec-impl-beads\",
      \"prefix\": \"bd\",
      \"server_user\": \"livespec-impl-beads\",
      \"database\": \"livespec-impl-beads\",
      \"bd_path\": \"bd\",
      \"fake\": true
    }
"""
        + dispatcher
        + """
  }
}
""",
        encoding="utf-8",
    )


def _stub_spec_output() -> SpecNextOutput:
    """A deterministic spec-`next` adaptation used to keep composition tests hermetic."""
    return SpecNextOutput(
        op="revise",
        spec_target="SPECIFICATION",
        summary="Revise a pending proposed change.",
        command="codex exec livespec:revise --project-root /workspace/livespec",
        urgency="medium",
    )


def _stub_spec_next(monkeypatch: pytest.MonkeyPatch, *, output: SpecNextOutput | None) -> None:
    """Replace `spec_next` so `build_attention` never touches a live CORE checkout."""

    def _fake(*, project_root: Path) -> SpecNextOutput | None:
        _ = project_root
        return output

    monkeypatch.setattr(needs_attention, "spec_next", _fake)


def _item(
    *,
    id_: str,
    status: str,
    type_: str = "task",
    rank: str = "a2",
    blocked_reason: str | None = None,
    factory_safety: str | None = None,
    admission_policy: str | None = None,
    acceptance_policy: str | None = None,
    spec_commitment_hint: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type=type_,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=blocked_reason,  # type: ignore[arg-type]
        factory_safety=factory_safety,  # type: ignore[arg-type]
        admission_policy=admission_policy,  # type: ignore[arg-type]
        acceptance_policy=acceptance_policy,  # type: ignore[arg-type]
        spec_commitment_hint=spec_commitment_hint,
    )


def _write_journal_record(project_root: Path, *, record: dict[str, Any]) -> None:
    journal = project_root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_dispatch_lock(project_root: Path, *, work_item_id: str) -> None:
    _ = write_dispatch_lock(
        repo=project_root,
        work_item_id=work_item_id,
        dispatch_id=f"run-{work_item_id}",
    )


def test_build_attention_composes_impl_human_valves_plan_threads_and_spec_next(
    tmp_path, monkeypatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    _ = (tmp_path / "plan" / "needs-attention").mkdir(parents=True)
    _seed(_item(id_="bd-ready", status="ready", rank="a1"))
    _seed(_item(id_="bd-approval", status="pending-approval", rank="a2"))
    _seed(_item(id_="bd-accept", status="acceptance", rank="a3"))
    _seed(_item(id_="bd-block", status="blocked", rank="a4", blocked_reason="needs-human"))

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.id for item in attention] == [
        "valve:approve:bd-approval",
        "valve:accept:bd-accept",
        "valve:resolve-blocked:bd-block",
        "impl:bd-ready",
        "spec:revise:SPECIFICATION",
        "plan:needs-attention",
        # Nothing is claimed and `bd-ready` is admission-eligible, so this
        # fixture is an idle factory by construction.
        "hygiene:idle-factory:repo",
    ]
    assert attention[0].handoff.action_id == "approve:bd-approval"
    assert attention[1].handoff.command.endswith("--action accept:bd-accept --json")
    assert attention[3].handoff.command.endswith("--action impl:bd-ready --json")
    assert attention[5].source_ref.path == "plan/needs-attention/"


def test_build_attention_reads_ledger_held_plan_without_handoff_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(
        _item(
            id_="bd-plan",
            type_="epic",
            status="backlog",
            rank="a1",
            spec_commitment_hint="plan:ledger-held",
        )
    )
    append_handoff(
        config=_config(),
        epic_id="bd-plan",
        body="Next action: keep driving bd-plan from the ledger.",
        author="factory-test",
        now="2026-08-11T01:02:03Z",
        next_action=NextAction(kind="impl", ref="bd-plan", text="Keep driving bd-plan."),
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not (tmp_path / "plan" / "ledger-held" / "handoff.md").exists()
    [plan_item] = [item for item in attention if item.id == "plan:ledger-held"]
    assert plan_item.summary == "Review plan ledger-held."
    assert plan_item.source_ref.path == "plan/ledger-held/"


def test_build_attention_surfaces_a_live_plan_with_an_insufficient_newest_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(
        _item(
            id_="bd-plan",
            type_="epic",
            status="backlog",
            rank="a1",
            spec_commitment_hint="plan:bad-handoff",
        )
    )
    append_handoff(
        config=_config(),
        epic_id="bd-plan",
        body="Current state cites bd-ib-qfv9.1.\n\n== EXACTLY ONE NEXT ACTION ==\nImplement it.",
        author="factory-test",
        now="2026-08-11T01:02:03Z",
        next_action=NextAction(kind="impl", ref="bd-ib-qfv9.1", text="Implement it."),
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    [plan_item] = [item for item in attention if item.id == "plan:bad-handoff"]
    assert plan_item.urgency == "high"
    assert (
        plan_item.summary
        == "Repair plan bad-handoff handoff: newest handoff records 0 next actions, not exactly one."
    )


def test_build_attention_advertises_approve_only_for_effective_manual_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, auto_approve_ready=True)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-auto", status="pending-approval", rank="a1"))
    _seed(
        _item(
            id_="bd-manual",
            status="pending-approval",
            rank="a2",
            admission_policy="manual",
        )
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.id for item in attention] == [
        "valve:approve:bd-manual",
        "hygiene:awaiting-admission:bd-auto",
        # The effective-`auto` item is admission-eligible and nothing is
        # claimed, so the same pass reports the factory as idle.
        "hygiene:idle-factory:repo",
    ]
    assert attention[0].handoff.action_id == "approve:bd-manual"
    assert attention[1].kind == "internal"
    assert "Dispatcher admission pass" in attention[1].summary


def test_build_attention_surfaces_ready_factory_safety_item_as_host_only(
    tmp_path, monkeypatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(
        _item(
            id_="bd-host",
            status="ready",
            rank="a1",
            factory_safety="needs-host-secrets",
        )
    )
    _seed(_item(id_="bd-ready", status="ready", rank="a2"))

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [(item.id, item.kind, item.handoff.kind) for item in attention] == [
        ("impl:bd-ready", "impl", "drive"),
        ("host-only:needs-host-secrets:bd-host", "host-only", "shell"),
        # The host-only row is NOT admission-eligible, so the idle-factory fact
        # that follows names `bd-ready` — the only dispatchable row here.
        ("hygiene:idle-factory:repo", "hygiene", "drive"),
    ]
    host_only = attention[1]
    assert host_only.source_ref.work_item == "bd-host"
    assert "bd-host" in host_only.summary
    assert str(tmp_path) in host_only.handoff.command
    assert "< /dev/null" in host_only.handoff.command


def test_build_attention_surfaces_recorded_factory_safety_refusal(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _write_journal_record(
        tmp_path,
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": "bd-recorded",
                "status": "failed",
                "stage": "host-only-refused",
                "pr_number": None,
                "merge_sha": None,
                "detail": "factory-safety refusal",
            },
        },
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [(item.id, item.kind, item.handoff.kind) for item in attention] == [
        ("host-only:recorded-refusal:bd-recorded", "host-only", "shell")
    ]


def test_build_attention_surfaces_unexpired_provider_exhaustion_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-held", status="ready", rank="a1"))
    _write_journal_record(
        tmp_path,
        record={
            "stage": "provider-exhaustion-observed",
            "work_item_id": "bd-prior",
            "provider": "codex",
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2099-01-01T00:00:00Z",
        },
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [(item.id, item.kind, item.handoff.kind) for item in attention] == [
        ("hygiene:provider-exhaustion:codex:bd-held", "internal", "shell")
    ]
    [held] = attention
    assert held.source_ref.work_item == "bd-held"
    assert "provider=codex" in held.summary
    assert "record_expires_at=2099-01-01T00:00:00Z" in held.summary
    assert "Dispatcher admission pass" in held.handoff.command


def test_build_attention_enriches_needs_attention_parked_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(
        _item(
            id_="bd-parked",
            status="acceptance",
            rank="a1",
            acceptance_policy="human-only",
        )
    )
    _write_journal_record(
        tmp_path,
        record={
            "stage": "acceptance-ai-pass",
            "work_item_id": "bd-parked",
            "verdict": "NEEDS_ATTENTION",
            "acceptance_policy": "human-only",
            "diff": {"observed": False, "reason": "missing-merge-evidence"},
            "criteria": {"observed": True, "checks": []},
            "telemetry": {"observed": False, "reason": "missing-run-turn"},
        },
    )
    _write_journal_record(
        tmp_path,
        record={
            "stage": "acceptance-parked",
            "work_item_id": "bd-parked",
            "policy": "human-only",
            "advisory": True,
            "acceptance_verdict": "NEEDS_ATTENTION",
        },
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.id for item in attention] == ["valve:accept:bd-parked"]
    [parked] = attention
    assert parked.kind == "human-valve"
    assert parked.handoff.action_id == "accept:bd-parked"
    assert "reject:bd-parked:rework" in parked.summary
    assert "reject:bd-parked:regroom" in parked.summary
    assert "NEEDS_ATTENTION" in parked.summary
    assert "absent evidence: diff, telemetry" in parked.summary


def test_build_attention_names_the_empty_diff_leg_on_a_zero_change_park(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero-change merged run composes as ONE attention item naming the empty-diff leg.

    The park is the one the empty-merged-diff refusal produces: telemetry and
    criteria were both observed, and the ONLY absent leg is the merged diff the
    pass read as changing zero files. It composes through the existing
    NEEDS_ATTENTION-parked-acceptance class — the `accept` human valve, no new
    attention kind — and its summary names that leg as the empty-diff leg rather
    than as a diff nobody could read, per the parked-acceptance arity and
    distinguishability rule of `SPECIFICATION/contracts.md`.
    """
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(
        _item(
            id_="bd-zero-change",
            status="acceptance",
            rank="a1",
            acceptance_policy="ai-only",
        )
    )
    _write_journal_record(
        tmp_path,
        record={
            "stage": "acceptance-ai-pass",
            "work_item_id": "bd-zero-change",
            "verdict": "NEEDS_ATTENTION",
            "acceptance_policy": "ai-only",
            "absent_evidence": ["empty merged diff"],
            "change_classification": {
                "classification": "change-implying",
                "declared_marker": None,
            },
            "diff": {"observed": False, "bytes": 0, "reason": "merged diff is empty"},
            "criteria": {"observed": True, "checks": []},
            "telemetry": {"observed": True, "passed": True, "reason": "green merged dispatch"},
        },
    )
    _write_journal_record(
        tmp_path,
        record={
            "stage": "acceptance-parked",
            "work_item_id": "bd-zero-change",
            "policy": "ai-only",
            "advisory": False,
            "acceptance_verdict": "NEEDS_ATTENTION",
            "absent_evidence": ["empty merged diff"],
        },
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    # Exactly ONE attention item, through the class that already exists.
    assert [item.id for item in attention] == ["valve:accept:bd-zero-change"]
    [parked] = attention
    assert parked.kind == "human-valve"
    assert parked.handoff.action_id == "accept:bd-zero-change"
    assert "NEEDS_ATTENTION" in parked.summary
    # The empty-diff merged-diff leg is named as the absent-evidence leg, so a
    # zero-change merge surfaces as itself and not as an unreadable diff.
    assert "absent evidence: empty merged diff." in parked.summary
    assert "reject:bd-zero-change:rework" in parked.summary
    assert "reject:bd-zero-change:regroom" in parked.summary


def test_build_attention_surfaces_stranded_merged_dispatch(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-active", status="active"))
    _write_journal_record(
        tmp_path,
        record={
            "stage": "outcome",
            "outcome": {
                "work_item_id": "bd-active",
                "status": "failed",
                "stage": "janitor-post-merge",
                "pr_number": 836,
                "merge_sha": "ba9fdafef895",
                "detail": "post-merge janitor red",
            },
        },
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [(item.id, item.kind, item.handoff.kind) for item in attention] == [
        ("host-only:stranded-dispatch:bd-active", "host-only", "shell")
    ]
    stranded = attention[0]
    assert "PR #836" in stranded.summary
    assert "janitor-post-merge" in stranded.summary
    assert "reconcile-merged" in stranded.handoff.command
    assert "--item bd-active" in stranded.handoff.command


def test_build_attention_surfaces_a_held_item_once_and_never_as_stranded(
    tmp_path, monkeypatch
) -> None:
    """The composed snapshot is the subject here, not any one gather primitive.

    A hold parks an item in the exact shape the stranded lane reads as a leaked
    claim, so the two facts are decided by one snapshot or they are not decided
    at all: asserting an intermediate gather result could show the hold row
    being BUILT while the stranded row it must displace still reached the wire.
    Reading the ids back from `build_attention` is also what proves the ONE-row
    clause, because a second producer for the same hold would appear here.

    The unheld sibling carrying identical journal evidence is the control. It
    still surfaces as stranded, which is what makes the held item's absence from
    that lane the discriminator's doing rather than the fixture's.
    """
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    for item_id in ("bd-held", "bd-loose"):
        _seed(_item(id_=item_id, status="active"))
        _write_journal_record(
            tmp_path,
            record={
                "stage": "outcome",
                "outcome": {
                    "work_item_id": item_id,
                    "status": "failed",
                    "stage": "janitor-post-merge",
                    "pr_number": 2211,
                    "merge_sha": "ba9fdafef895",
                },
            },
        )
    update_work_item_merge_hold(path=_config(), item_id="bd-held", value=True)

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    ids = [item.id for item in attention]
    assert ids.count("hygiene:merge-hold:bd-held") == 1
    assert "host-only:stranded-dispatch:bd-held" not in ids
    assert "host-only:stranded-dispatch:bd-loose" in ids
    assert "hygiene:merge-hold:bd-loose" not in ids
    [held] = [item for item in attention if item.id == "hygiene:merge-hold:bd-held"]
    assert held.kind == "hygiene"
    assert "pull request #2211" in held.summary
    assert held.handoff.action_id == "set-merge-hold:bd-held:off"
    assert "--action set-merge-hold:bd-held:off" in held.handoff.command


def test_build_attention_retracts_the_merge_hold_row_when_the_hold_is_released(
    tmp_path, monkeypatch
) -> None:
    """The row STANDS until release, and then it is gone — no clock, no dwell.

    Composed twice over the same tenant, so the retraction is observed as a
    state change rather than inferred from a second fixture that was never held.
    """
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-held", status="active"))
    update_work_item_merge_hold(path=_config(), item_id="bd-held", value=True)
    while_held = build_attention(project_root=tmp_path, repo_name="repo", include_hygiene=False)

    update_work_item_merge_hold(path=_config(), item_id="bd-held", value=False)
    after_release = build_attention(project_root=tmp_path, repo_name="repo", include_hygiene=False)

    assert "hygiene:merge-hold:bd-held" in [item.id for item in while_held]
    assert "hygiene:merge-hold:bd-held" not in [item.id for item in after_release]


def test_build_attention_composes_capacity_residue_from_accounting(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path, auto_approve_ready=True, wip_cap=2)
    _stub_spec_next(monkeypatch, output=None)
    live = _item(id_="bd-live", status="active")
    unreadable = _item(id_="bd-unreadable", status="active")
    for item in (live, unreadable):
        _seed(item)
    _write_dispatch_lock(tmp_path, work_item_id=live.id)
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.mkdir(parents=True)
    original_journal = b""

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    capacity_items = [item for item in attention if item.id.startswith("hygiene:capacity")]
    assert [item.id for item in capacity_items] == [
        "hygiene:capacity:repo",
        "hygiene:capacity-hold:bd-unreadable",
    ]
    assert (
        capacity_items[0].summary
        == "Capacity reached for repo: 2 counted claims, 0 free slots under per-repo WIP cap 2; host-run concurrency is governed separately."
    )
    assert "codex exec" in capacity_items[0].handoff.command
    assert "inspect-capacity repo" in capacity_items[0].handoff.command
    assert capacity_items[1].source_ref.work_item == unreadable.id
    assert "Inspect capacity hold bd-unreadable" in capacity_items[1].summary
    assert "inspect-capacity-hold" in capacity_items[1].handoff.command
    assert "release-to-ready" not in capacity_items[1].handoff.command
    assert "bd-live" not in [item.id for item in capacity_items]
    assert not any(item.id == "host-only:stranded-dispatch:bd-unreadable" for item in attention)
    assert journal.is_dir()
    assert original_journal == b""


def test_build_attention_surfaces_ready_aging_fact_after_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-oldest", status="ready", rank="a1"))
    _seed(_item(id_="bd-younger", status="ready", rank="a2"))
    _set_ready_since(id_="bd-oldest", ready_since="2026-08-24T00:00:00Z")
    _set_ready_since(id_="bd-younger", ready_since="2026-08-25T12:00:00Z")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    [aging] = [item for item in attention if item.id == "hygiene:ready-aging:repo"]
    assert aging.kind == "hygiene"
    assert aging.urgency == "high"
    assert aging.source_ref.repo == "repo"
    assert aging.source_ref.work_item is None
    assert "1 ready work-item has waited past 24h" in aging.summary
    assert "oldest age 60h" in aging.summary
    assert "oldest work-item bd-oldest" in aging.summary
    assert "Unblock handoff: start or inspect the Dispatcher admission pass" in aging.summary
    assert "ready-aging repo" in aging.handoff.command
    assert str(tmp_path) in aging.handoff.command
    assert "< /dev/null" in aging.handoff.command


def test_build_attention_omits_ready_aging_when_dispatch_lock_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-old", status="ready", rank="a1"))
    _set_ready_since(id_="bd-old", ready_since="2026-08-24T00:00:00Z")
    _write_dispatch_lock(tmp_path, work_item_id="bd-old")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not any(item.id == "hygiene:ready-aging:repo" for item in attention)


def test_build_attention_omits_ready_aging_when_watchable_run_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-old", status="ready", rank="a1"))
    _set_ready_since(id_="bd-old", ready_since="2026-08-24T00:00:00Z")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )

    def _watchable_item_ids(*, repo: Path) -> frozenset[str]:
        _ = repo
        return frozenset({"bd-old"})

    monkeypatch.setattr(
        needs_attention,
        "watchable_fabro_run_item_ids",
        _watchable_item_ids,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not any(item.id == "hygiene:ready-aging:repo" for item in attention)


def test_build_attention_checks_watchable_runs_once_for_ready_aging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    for item_id in ("bd-old-1", "bd-old-2", "bd-old-3"):
        _seed(_item(id_=item_id, status="ready", rank="a1"))
        _set_ready_since(id_=item_id, ready_since="2026-08-24T00:00:00Z")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )
    calls: list[Path] = []

    def _watchable_item_ids(*, repo: Path) -> frozenset[str]:
        calls.append(repo)
        return frozenset()

    monkeypatch.setattr(
        needs_attention,
        "watchable_fabro_run_item_ids",
        _watchable_item_ids,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert calls == [tmp_path]
    assert any(item.id == "hygiene:ready-aging:repo" for item in attention)


def test_build_attention_omits_ready_aging_when_no_ready_item_exceeds_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-fresh", status="ready", rank="a1"))
    _set_ready_since(id_="bd-fresh", ready_since="2026-08-26T00:00:00Z")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not any(item.id == "hygiene:ready-aging:repo" for item in attention)


def test_build_attention_reports_unknown_ready_age_with_aged_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(tmp_path, ready_aging_threshold_hours=24)
    _stub_spec_next(monkeypatch, output=None)
    _seed(_item(id_="bd-aged", status="ready", rank="a1"))
    _seed(_item(id_="bd-unknown", status="ready", rank="a2"))
    _set_ready_since(id_="bd-aged", ready_since="2026-08-24T00:00:00Z")
    _set_ready_since(id_="bd-unknown", ready_since="not-a-date")
    monkeypatch.setattr(
        needs_attention,
        "_utc_now_iso",
        lambda: "2026-08-26T12:00:00Z",
        raising=False,
    )

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    [aging] = [item for item in attention if item.id == "hygiene:ready-aging:repo"]
    assert "1 ready work-item has waited past 24h" in aging.summary
    assert "age-unknown: bd-unknown" in aging.summary


def test_watchable_fabro_run_lookup_returns_none_when_ps_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = __import__(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items",
        fromlist=["_needs_attention_work_items"],
    )
    assert hasattr(module, "watchable_fabro_run_lookup")

    class _Command:
        exit_code = 1

    class _PsResult:
        command = _Command()
        runs = ()

    class _FabroPort:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs

        def ps(self, *, timeout_seconds: float) -> _PsResult:
            _ = timeout_seconds
            return _PsResult()

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items.FabroPort",
        _FabroPort,
    )

    assert module.watchable_fabro_run_lookup(repo=tmp_path, work_item_id="bd-run") is None


def test_watchable_fabro_run_item_ids_returns_empty_when_ps_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = __import__(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items",
        fromlist=["_needs_attention_work_items"],
    )
    assert hasattr(module, "watchable_fabro_run_item_ids")

    class _Command:
        exit_code = 1

    class _PsResult:
        command = _Command()
        runs = ()

    class _FabroPort:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs

        def ps(self, *, timeout_seconds: float) -> _PsResult:
            _ = timeout_seconds
            return _PsResult()

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._needs_attention_work_items.FabroPort",
        _FabroPort,
    )

    assert module.watchable_fabro_run_item_ids(repo=tmp_path) == frozenset()


def test_build_attention_omits_capacity_when_all_counted_holds_are_live(
    tmp_path, monkeypatch
) -> None:
    _write_config(tmp_path, auto_approve_ready=True, wip_cap=2)
    _stub_spec_next(monkeypatch, output=None)
    first = _item(id_="bd-live-a", status="active")
    second = _item(id_="bd-live-b", status="active")
    for item in (first, second):
        _seed(item)
        _write_dispatch_lock(tmp_path, work_item_id=item.id)

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not any(item.id.startswith("hygiene:capacity") for item in attention)


def test_build_attention_reads_capacity_count_from_accounting_verdict(
    tmp_path, monkeypatch
) -> None:
    _write_config(tmp_path, auto_approve_ready=True, wip_cap=2)
    _stub_spec_next(monkeypatch, output=None)
    live = _item(id_="bd-live", status="active")
    no_outcome = _item(id_="bd-no-outcome", status="active")
    for item in (live, no_outcome):
        _seed(item)
    _write_dispatch_lock(tmp_path, work_item_id=live.id)
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert not any(item.id.startswith("hygiene:capacity") for item in attention)


def test_build_attention_surfaces_untriaged_backlog_and_summarizes_the_remainder(
    tmp_path, monkeypatch
) -> None:
    """The load-bearing case: a backlog item the intake gate never saw is visible.

    `livespec-h95t` — an item filed with a raw `bd create` lands in
    `backlog`, which no dispatch surface admits and no attention lane
    reported, so it was indistinguishable from a deliberately-parked epic.
    The `intake:triaged` marker is the discriminator: gated items carry it,
    this one does not. Noise control is part of the contract — P0/P1 get one
    lane each, everything at P2 or lower collapses into ONE summary lane.
    """
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed_raw(id_="bd-p0", status="backlog", priority=0, title="Un-triaged P0")
    _seed_raw(id_="bd-p1", status="backlog", priority=1, title="Un-triaged P1")
    _seed_raw(id_="bd-p2", status="backlog", priority=2, title="Un-triaged P2")
    _seed_raw(id_="bd-p3", status="backlog", priority=3, title="Un-triaged P3")

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [(item.id, item.kind, item.urgency) for item in attention] == [
        ("hygiene:untriaged-backlog:bd-p0", "hygiene", "high"),
        ("hygiene:untriaged-backlog:bd-p1", "hygiene", "high"),
        ("hygiene:untriaged-backlog-remainder:count", "hygiene", "low"),
    ]
    assert attention[0].source_ref.work_item == "bd-p0"
    assert "Un-triaged P0" in attention[0].summary
    remainder = attention[2]
    assert remainder.source_ref.work_item is None
    assert "2 un-triaged backlog work-items at P2 or lower" in remainder.summary


def test_build_attention_omits_triaged_backlog_and_non_backlog_items(tmp_path, monkeypatch) -> None:
    """The marker dismisses an item; a non-backlog status is never in this lane.

    A deliberately-parked epic the intake gate routed to `backlog` carries
    `intake:triaged`, so it stays silent — that is the whole point of the
    discriminator. A P0 item in any other status belongs to another lane.
    """
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    _seed_raw(id_="bd-parked", status="backlog", priority=0, labels=["intake:triaged"])
    _seed_raw(id_="bd-elsewhere", status="ready", priority=0)

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    # Scoped to this lane's own id family: the ready `bd-elsewhere` row makes
    # the same pass an idle factory, and that unrelated hygiene fact would
    # otherwise read as an untriaged-backlog emission.
    assert [item.id for item in attention if item.id.startswith("hygiene:untriaged-backlog")] == []


def test_build_attention_drops_spec_item_when_spec_next_none(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)

    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    assert [item.kind for item in attention if item.kind == "spec"] == []


def test_render_json_wraps_flat_attention_array(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    payload = json.loads(render_json(attention=attention))

    assert list(payload) == ["attention"]
    assert payload["attention"][0]["id"] == "spec:revise:SPECIFICATION"


def test_render_markdown_lists_handoff_commands(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    attention = build_attention(
        project_root=tmp_path,
        repo_name="repo",
        include_hygiene=False,
    )

    rendered = render_markdown(attention=attention)

    assert rendered.startswith("# Needs Attention\n")
    assert "`spec:revise:SPECIFICATION`" in rendered
    assert "codex exec livespec:revise" in rendered


def test_render_markdown_empty_attention() -> None:
    assert render_markdown(attention=[]) == "No attention items.\n"


def test_main_json_output(
    tmp_path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    rc = main(
        argv=["--json", "--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["attention"][0]["id"] == "spec:revise:SPECIFICATION"


def test_main_markdown_output(
    tmp_path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=_stub_spec_output())
    rc = main(argv=["--skip-hygiene", "--project-root", str(tmp_path), "--repo-name", "repo"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("# Needs Attention\n")


def test_build_attention_composes_the_release_adoption_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adoption fact reaches the snapshot, and a current adopter is named.

    The lane's own derivation is covered beside it; what this asserts is the
    WIRING plus the positive half — a snapshot that could only ever report
    adopters as behind would be indistinguishable from one that had stopped
    reading the install records at all.

    The registries below are keyed on THIS plugin's real name while the project
    under test declares a different one in its own manifest, which is the shape
    every governed repository actually has. Keying the fixture on the project's
    own name instead would let a lane that looked the plugin up from
    `project_root` pass this test while emitting nothing in the entire fleet.
    """
    from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
        ReleaseAdoptionBases,
    )

    _write_config(tmp_path)
    _stub_spec_next(monkeypatch, output=None)
    registries = tmp_path / "registries"
    builds = tmp_path / "builds"

    def _plant(path: Path, payload: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    plugin = "livespec-orchestrator-beads-fabro"
    _ = _plant(
        tmp_path / ".claude-plugin" / "plugin.json",
        {"name": "the-governed-project", "version": "1.2.0"},
    )
    _ = _plant(builds / "tip" / "plugin.json", {"name": plugin, "version": "1.2.0"})
    _ = _plant(builds / "stale" / "plugin.json", {"name": plugin, "version": "1.1.0"})
    marketplace = _plant(
        registries / "known_marketplaces.json",
        {plugin: {"source": {"ref": "release"}, "installLocation": str(builds / "tip")}},
    )
    installed = _plant(
        registries / "installed_plugins.json",
        {
            "plugins": {
                f"{plugin}@{plugin}": [
                    {
                        "projectPath": str(tmp_path / "p" / "on-tip"),
                        "installPath": str(builds / "tip"),
                    },
                    {
                        "projectPath": str(tmp_path / "p" / "lagging"),
                        "installPath": str(builds / "stale"),
                    },
                ]
            }
        },
    )
    monkeypatch.setattr(
        needs_attention,
        "default_release_adoption_bases",
        lambda: ReleaseAdoptionBases(install_record=installed, marketplace_record=marketplace),
    )

    attention = build_attention(project_root=tmp_path, repo_name="repo", include_hygiene=False)

    adoption = {
        item.id: item for item in attention if item.id.startswith("hygiene:release-adoption:")
    }
    assert sorted(adoption) == [
        "hygiene:release-adoption:lagging",
        "hygiene:release-adoption:on-tip",
    ]
    assert "BEHIND" in adoption["hygiene:release-adoption:lagging"].summary
    assert adoption["hygiene:release-adoption:lagging"].urgency == "high"
    assert "BEHIND" not in adoption["hygiene:release-adoption:on-tip"].summary
    assert adoption["hygiene:release-adoption:on-tip"].urgency == "low"

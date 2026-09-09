"""Tests for the beads-backed store mutation primitives."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    FakeBeadsClient,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro._store_mutations import (
    append_work_item,
    register_custom_statuses,
    update_work_item_rank,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import (
    AuditRecord,
    StoreConfig,
    WorkItem,
    WorkItemStatus,
)
from livespec_runtime.work_items.types import (
    AcceptancePolicy,
    AdmissionPolicy,
    Origin,
    Resolution,
    StoredBlockedReason,
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _minimal_work_item(
    *,
    id_: str = "li-aaa111",
    status: WorkItemStatus = "ready",
    origin: Origin = "freeform",
    gap_id: str | None = None,
    resolution: Resolution | None = None,
    reason: str | None = None,
    audit: AuditRecord | None = None,
    depends_on: tuple[object, ...] = (),
    superseded_by: str | None = None,
    spec_commitment_hint: str | None = None,
    rank: str = "a0",
    assignee: str | None = None,
    admission_policy: AdmissionPolicy | None = None,
    acceptance_policy: AcceptancePolicy | None = None,
    blocked_reason: StoredBlockedReason | None = None,
    acceptance_criteria: str | None = None,
    notes: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,
        title="t",
        description="d",
        origin=origin,
        gap_id=gap_id,
        rank=rank,
        assignee=assignee,
        depends_on=depends_on,
        captured_at="2026-05-19T00:00:00Z",
        resolution=resolution,
        reason=reason,
        audit=audit,
        superseded_by=superseded_by,
        spec_commitment_hint=spec_commitment_hint,
        acceptance_criteria=acceptance_criteria,
        notes=notes,
        admission_policy=admission_policy,
        acceptance_policy=acceptance_policy,
        blocked_reason=blocked_reason,
    )


def test_append_then_read_ready_work_item_roundtrips() -> None:
    item = _minimal_work_item()
    append_work_item(path=_config(), item=item)
    [read_back] = list(read_work_items(path=_config()))
    assert read_back == item


def test_update_work_item_rank_rekeys_in_place_leaving_other_fields() -> None:
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-rk", rank="a2", assignee="alice", origin="gap-tied", gap_id="G1"
        ),
    )
    update_work_item_rank(path=_config(), item=_minimal_work_item(id_="li-rk", rank="a8"))
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.rank == "a8"
    assert read_back.assignee == "alice"
    assert read_back.gap_id == "G1"
    assert read_back.status == "ready"


def test_update_work_item_status_transitions_and_sets_assignee_in_place() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-st", status="ready"))
    update_work_item_status(path=_config(), item_id="li-st", status="active", assignee="fabro")
    [read_back] = list(read_work_items(path=_config()))
    assert (read_back.status, read_back.assignee) == ("active", "fabro")
    update_work_item_status(path=_config(), item_id="li-st", status="acceptance")
    [read_back] = list(read_work_items(path=_config()))
    assert (read_back.status, read_back.assignee) == ("acceptance", "fabro")


def test_update_work_item_status_writes_an_assigned_rank_in_the_same_mutation() -> None:
    """The adoption seam writes status AND rank at once, keeping unmodeled keys.

    The unmodeled key is the discriminator: a rank write that rebuilt metadata
    from scratch would leave the status right and silently drop it.
    """
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-adopt", status="backlog", rank="a2"),
    )
    _fake().update_issue(issue_id="li-adopt", metadata={"rank": "a2", "unmodeled": "keep-me"})

    update_work_item_status(path=_config(), item_id="li-adopt", status="active", rank="a6")

    [read_back] = list(read_work_items(path=_config()))
    assert (read_back.status, read_back.rank) == ("active", "a6")
    assert _fake().show_issue(issue_id="li-adopt")["metadata"] == {
        "rank": "a6",
        "unmodeled": "keep-me",
    }


def test_transitions_out_of_active_clear_the_rework_pending_marker() -> None:
    """The clear rides the write SEAMS, so no disposition can forget it.

    Three seams carry a transition out of `active` — the ordinary status write,
    the blocked-state escalation, and the terminal close — and each is checked
    here, because the standing invariant is that an item whose status is not
    `active` never carries the marker.
    """
    for item_id in ("li-mark-status", "li-mark-blocked", "li-mark-closed"):
        append_work_item(path=_config(), item=_minimal_work_item(id_=item_id, status="ready"))
        update_work_item_status(path=_config(), item_id=item_id, status="active")
        update_work_item_rework_pending(path=_config(), item_id=item_id, value=True)

    update_work_item_status(path=_config(), item_id="li-mark-status", status="acceptance")
    update_work_item_blocked_state(
        path=_config(),
        item_id="li-mark-blocked",
        status="blocked",
        blocked_reason="needs-human",
    )
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-mark-closed", status="done", resolution="completed"),
    )

    read_back = {item.id: item for item in read_work_items(path=_config())}
    assert [read_back[item_id].rework_pending for item_id in sorted(read_back)] == [
        False,
        False,
        False,
    ]


def test_a_transition_into_active_leaves_the_rework_pending_marker_in_place() -> None:
    """The control for the clear above: a rework re-dispatch must not lose it."""
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-mark-kept", status="active"))
    update_work_item_rework_pending(path=_config(), item_id="li-mark-kept", value=True)

    update_work_item_status(
        path=_config(), item_id="li-mark-kept", status="active", assignee="fabro"
    )

    [read_back] = list(read_work_items(path=_config()))
    assert (read_back.status, read_back.rework_pending) == ("active", True)


def test_update_work_item_status_can_explicitly_clear_assignee() -> None:
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-clear", status="active", assignee="fabro"),
    )

    update_work_item_status(
        path=_config(),
        item_id="li-clear",
        status="ready",
        clear_assignee=True,
    )

    [read_back] = list(read_work_items(path=_config()))
    assert (read_back.status, read_back.assignee) == ("ready", None)


def test_append_ready_item_records_ready_dwell_instant(monkeypatch: pytest.MonkeyPatch) -> None:
    from livespec_orchestrator_beads_fabro import _store_mutations

    assert hasattr(_store_mutations, "read_ready_dwell_instants")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._store_mutations._utc_now_iso",
        lambda: "2026-08-25T12:00:00Z",
    )

    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-ready-since",
            status="ready",
            rank="a1",
        ),
    )

    record = _fake().show_issue(issue_id="li-ready-since")
    assert record["created_at"] == "2026-05-19T00:00:00Z"
    assert record["metadata"]["ready_since"] == "2026-08-25T12:00:00Z"
    assert _store_mutations.read_ready_dwell_instants(path=_config()) == {
        "li-ready-since": "2026-08-25T12:00:00Z"
    }


def test_reentering_ready_records_new_ready_dwell_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter(
        [
            "2026-08-25T12:00:00Z",
            "2026-08-25T12:30:00Z",
        ]
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._store_mutations._utc_now_iso",
        lambda: next(times),
    )
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-reentry"))

    update_work_item_status(path=_config(), item_id="li-reentry", status="active")
    update_work_item_status(path=_config(), item_id="li-reentry", status="ready")

    assert _fake().show_issue(issue_id="li-reentry")["metadata"]["ready_since"] == (
        "2026-08-25T12:30:00Z"
    )


def test_ready_dwell_projection_reports_missing_instant_as_unknown() -> None:
    from livespec_orchestrator_beads_fabro import _store_mutations

    assert hasattr(_store_mutations, "read_ready_dwell_instants")
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-known", status="ready"))
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-legacy", status="backlog"))
    _fake().update_issue(issue_id="li-legacy", status="ready", metadata={"rank": "a0"})

    assert _store_mutations.read_ready_dwell_instants(path=_config()) == {
        "li-known": _fake().show_issue(issue_id="li-known")["metadata"]["ready_since"],
        "li-legacy": None,
    }


def test_append_lands_custom_status_via_two_step() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-bk", status="backlog"))
    record = _fake().show_issue(issue_id="li-bk")
    assert record["status"] == "backlog"
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.status == "backlog"


def test_register_custom_statuses_provisions_the_tenant() -> None:
    register_custom_statuses(path=_config())
    assert _fake().custom_statuses_registered is True


def test_created_item_carries_labels_metadata_and_spec_hint() -> None:
    audit = AuditRecord(
        verification_timestamp="2026-05-19T01:00:00Z",
        commits=("deadbeef",),
        files_changed=("a.py",),
        merge_sha="abc123",
        pr_number=42,
    )
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-full",
            origin="gap-tied",
            gap_id="G7",
            resolution="completed",
            audit=audit,
            spec_commitment_hint="topic-x",
            acceptance_criteria="Run just check.",
            notes="Keep scope narrow.",
            admission_policy="manual",
            acceptance_policy="ai-then-human",
            blocked_reason="needs-human",
        ),
    )
    record = _fake().show_issue(issue_id="li-full")
    assert record["spec_id"] == "topic-x"
    assert "origin:gap-tied" in record["labels"]
    assert "gap-id:G7" in record["labels"]
    assert "resolution:completed" in record["labels"]
    assert "admission:manual" in record["labels"]
    assert "acceptance:ai-then-human" in record["labels"]
    assert "blocked-reason:needs-human" in record["labels"]
    assert record["metadata"]["audit"]["merge_sha"] == "abc123"
    assert record["metadata"]["audit"]["pr_number"] == 42
    assert record["acceptance_criteria"] == "Run just check."
    assert record["notes"] == "Keep scope narrow."
    assert "acceptance_criteria" not in record["metadata"]
    assert "notes" not in record["metadata"]


def test_native_acceptance_update_matches_plugin_read_projection() -> None:
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-edit",
            acceptance_criteria="Original acceptance.",
            notes="Original notes.",
        ),
    )

    _fake().update_issue(
        issue_id="li-edit",
        acceptance_criteria="Edited acceptance.",
        notes="Edited notes.",
    )

    record = _fake().show_issue(issue_id="li-edit")
    [read_back] = list(read_work_items(path=_config()))
    assert record["acceptance_criteria"] == read_back.acceptance_criteria
    assert record["notes"] == read_back.notes
    assert read_back.acceptance_criteria == "Edited acceptance."
    assert read_back.notes == "Edited notes."


def test_rank_update_does_not_clobber_concurrent_native_acceptance_edit() -> None:
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-concurrent",
            rank="a0",
            acceptance_criteria="Original acceptance.",
            notes="Original notes.",
        ),
    )
    stale_projection = next(iter(read_work_items(path=_config())))

    _fake().update_issue(
        issue_id="li-concurrent",
        acceptance_criteria="Concurrent acceptance.",
        notes="Concurrent notes.",
    )
    update_work_item_rank(path=_config(), item=stale_projection)

    record = _fake().show_issue(issue_id="li-concurrent")
    [read_back] = list(read_work_items(path=_config()))
    assert record["acceptance_criteria"] == "Concurrent acceptance."
    assert record["notes"] == "Concurrent notes."
    assert read_back.acceptance_criteria == "Concurrent acceptance."
    assert read_back.notes == "Concurrent notes."
    assert "acceptance_criteria" not in record["metadata"]
    assert "notes" not in record["metadata"]


def test_depends_on_edges_and_non_local_metadata_are_written() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-dep"))
    local_entry: dict[str, object] = {"kind": "local", "work_item_id": "li-dep"}
    non_local_entry: dict[str, object] = {
        "kind": "pull_request",
        "repo": "org/repo",
        "number": 42,
    }
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-x",
            depends_on=("li-bare", local_entry, non_local_entry, 42, {"kind": "local"}),
        ),
    )
    record = _fake().show_issue(issue_id="li-x")
    assert {"depends_on_id": "li-bare", "type": EDGE_BLOCKS} in record["dependencies"]
    assert {"depends_on_id": "li-dep", "type": EDGE_BLOCKS} in record["dependencies"]
    assert record["metadata"]["non_local_depends_on"] == [non_local_entry]


def test_superseded_by_maps_to_supersedes_edge_on_superseding_issue() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-new"))
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-old", superseded_by="li-new"))
    record = _fake().show_issue(issue_id="li-new")
    assert {"depends_on_id": "li-old", "type": EDGE_SUPERSEDES} in record["dependencies"]


def test_close_in_place_mutates_existing_record_no_second_record() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a", status="ready"))
    audit = AuditRecord(
        verification_timestamp="2026-05-19T02:00:00Z",
        commits=("c1",),
        files_changed=("f1",),
        merge_sha="sha-1",
        pr_number=11,
    )
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-a",
            status="done",
            resolution="completed",
            reason="shipped",
            audit=audit,
        ),
    )
    all_ids = [record["id"] for record in _fake().list_issues()]
    assert all_ids.count("li-a") == 1
    record = _fake().show_issue(issue_id="li-a")
    assert record["status"] == "closed"
    assert record["close_reason"] == "shipped"
    assert "resolution:completed" in record["labels"]
    assert record["metadata"]["audit"]["merge_sha"] == "sha-1"


def test_append_work_item_preserves_unmodeled_metadata_keys() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-unknown", status="ready"))
    _fake().update_issue(
        issue_id="li-unknown",
        metadata={
            "rank": "a0",
            "unmodeled_top_level": {"source": "raw-bd-update"},
            "audit": {
                "verification_timestamp": "2026-05-19T02:00:00Z",
                "commits": ["c1"],
                "files_changed": ["f1"],
                "merge_sha": "sha-1",
                "pr_number": 11,
                "supersedes": {"pr_number": 1519},
            },
        },
    )
    [stale_projection] = list(read_work_items(path=_config()))

    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-unknown",
            status="done",
            resolution="completed",
            reason="shipped",
            audit=stale_projection.audit,
        ),
    )

    metadata = _fake().show_issue(issue_id="li-unknown")["metadata"]
    _assert_unknown_metadata_preserved(metadata=metadata)
    stripped_metadata = {"rank": metadata["rank"], "audit": {"merge_sha": "sha-1"}}
    with pytest.raises(AssertionError):
        _assert_unknown_metadata_preserved(metadata=stripped_metadata)


def _assert_unknown_metadata_preserved(*, metadata: object) -> None:
    assert isinstance(metadata, dict)
    assert metadata.get("unmodeled_top_level") == {"source": "raw-bd-update"}
    audit = metadata.get("audit")
    assert isinstance(audit, dict)
    assert audit.get("supersedes") == {"pr_number": 1519}


def test_close_in_place_without_resolution_adds_no_resolution_label() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a", status="ready"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-a", status="done", reason="admin close"),
    )
    record = _fake().show_issue(issue_id="li-a")
    assert not any(label.startswith("resolution:") for label in record["labels"])
    assert record["status"] == "closed"


def test_append_born_closed_item_for_absent_id_creates_then_closes() -> None:
    audit = AuditRecord(
        verification_timestamp="2026-05-19T02:00:00Z",
        commits=("c",),
        files_changed=("f",),
        merge_sha="sha-3",
    )
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-born",
            status="done",
            resolution="completed",
            reason="done at birth",
            audit=audit,
        ),
    )
    all_ids = [record["id"] for record in _fake().list_issues()]
    assert all_ids.count("li-born") == 1
    record = _fake().show_issue(issue_id="li-born")
    assert record["status"] == "closed"
    assert "resolution:completed" in record["labels"]

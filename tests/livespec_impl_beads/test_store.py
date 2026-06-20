"""Tests for the beads-backed store primitives (hermetic FakeBeadsClient).

Every test drives the store through the in-memory `FakeBeadsClient` (the
autouse fixture in `conftest.py` sets `LIVESPEC_BEADS_FAKE=1` and resets the
process-singleton between cases). Round-trip tests go through the public
store functions; the typed `BeadsMappingError` paths are exercised by
injecting malformed records straight into the fake tenant via the client
seam.

Coverage targets the whole FIELD MAP:

- origin / gap_id → `origin:` / `gap-id:` labels
- resolution → `resolution:<enum>` label
- spec_commitment_hint → native `spec_id`
- audit (full AuditRecord) → `metadata` JSON (lossless, incl. merge_sha/pr_number)
- depends_on → `blocks` edges; superseded_by → `supersedes` edge
- close-in-place semantics (one record per id; resolution label + audit in
  metadata; NO second record)
"""

from __future__ import annotations

import pytest
from livespec_impl_beads._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    FakeBeadsClient,
    make_beads_client,
)
from livespec_impl_beads.errors import BeadsMappingError
from livespec_impl_beads.store import (
    WorkItemComment,
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_impl_beads.types import AuditRecord, StoreConfig, WorkItem


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
    """Return the process-singleton fake the store also talks to."""
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _minimal_work_item(
    *,
    id_: str = "li-aaa111",
    status: str = "open",
    origin: str = "freeform",
    gap_id: str | None = None,
    resolution: str | None = None,
    reason: str | None = None,
    audit: AuditRecord | None = None,
    depends_on: tuple[object, ...] = (),
    superseded_by: str | None = None,
    spec_commitment_hint: str | None = None,
    priority: int = 2,
    assignee: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title="t",
        description="d",
        origin=origin,  # type: ignore[arg-type]
        gap_id=gap_id,
        priority=priority,
        assignee=assignee,
        depends_on=depends_on,
        captured_at="2026-05-19T00:00:00Z",
        resolution=resolution,  # type: ignore[arg-type]
        reason=reason,
        audit=audit,
        superseded_by=superseded_by,
        spec_commitment_hint=spec_commitment_hint,
    )


# --------------------------------------------------------------------------
# Work-item read / append round-trips.
# --------------------------------------------------------------------------


def test_read_work_items_empty_tenant_yields_nothing() -> None:
    assert list(read_work_items(path=_config())) == []


def test_append_then_read_open_work_item_roundtrips() -> None:
    item = _minimal_work_item()
    append_work_item(path=_config(), item=item)
    [read_back] = list(read_work_items(path=_config()))
    assert read_back == item


def test_origin_and_gap_id_map_to_labels() -> None:
    item = _minimal_work_item(id_="li-gap", origin="gap-tied", gap_id="G7")
    append_work_item(path=_config(), item=item)
    record = _fake().show_issue(issue_id="li-gap")
    assert "origin:gap-tied" in record["labels"]
    assert "gap-id:G7" in record["labels"]
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "gap-tied"
    assert read_back.gap_id == "G7"


def test_spec_commitment_hint_maps_to_native_spec_id() -> None:
    item = _minimal_work_item(id_="li-hint", spec_commitment_hint="topic-x")
    append_work_item(path=_config(), item=item)
    record = _fake().show_issue(issue_id="li-hint")
    assert record["spec_id"] == "topic-x"
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.spec_commitment_hint == "topic-x"


def test_assignee_and_priority_roundtrip() -> None:
    item = _minimal_work_item(id_="li-pa", priority=0, assignee="alice")
    append_work_item(path=_config(), item=item)
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.priority == 0
    assert read_back.assignee == "alice"


def test_audit_maps_to_metadata_losslessly() -> None:
    audit = AuditRecord(
        verification_timestamp="2026-05-19T01:00:00Z",
        commits=("deadbeef",),
        files_changed=("a.py",),
        merge_sha="abc123",
        pr_number=42,
    )
    item = _minimal_work_item(
        id_="li-zzz999",
        status="closed",
        resolution="completed",
        reason="done",
        audit=audit,
    )
    append_work_item(path=_config(), item=item)
    record = _fake().show_issue(issue_id="li-zzz999")
    assert record["metadata"]["audit"]["merge_sha"] == "abc123"
    assert record["metadata"]["audit"]["pr_number"] == 42
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is not None
    assert read_back.audit.merge_sha == "abc123"
    assert read_back.audit.pr_number == 42
    assert read_back.audit.commits == ("deadbeef",)
    assert read_back.audit.files_changed == ("a.py",)


def test_audit_with_null_pr_number_roundtrips() -> None:
    audit = AuditRecord(
        verification_timestamp="2026-05-19T01:00:00Z",
        commits=(),
        files_changed=(),
        merge_sha="abc123def",
        pr_number=None,
    )
    item = _minimal_work_item(
        id_="li-merge8",
        status="closed",
        resolution="completed",
        audit=audit,
    )
    append_work_item(path=_config(), item=item)
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is not None
    assert read_back.audit.merge_sha == "abc123def"
    assert read_back.audit.pr_number is None


def test_work_item_without_audit_has_empty_metadata() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-noaudit"))
    record = _fake().show_issue(issue_id="li-noaudit")
    assert record["metadata"] == {}
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is None


# --------------------------------------------------------------------------
# depends_on (blocks) + superseded_by (supersedes) edges.
# --------------------------------------------------------------------------


def test_depends_on_bare_string_maps_to_blocks_edge_and_back() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-dep"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-blocked", depends_on=("li-dep",)),
    )
    record = _fake().show_issue(issue_id="li-blocked")
    assert {"depends_on_id": "li-dep", "type": EDGE_BLOCKS} in record["dependencies"]
    materialized = materialize_work_items(read_work_items(path=_config()))
    # The read path materializes each `blocks` edge as the v072 typed-dict
    # local entry, NOT the legacy bare string. livespec's DependsOnEntry
    # schema (and the doctor `depends_on-ref-wellformedness` check) require
    # the typed-dict form.
    assert materialized["li-blocked"].depends_on == ({"kind": "local", "work_item_id": "li-dep"},)


def test_depends_on_typed_local_dict_maps_to_blocks_edge() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-dep"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-blocked",
            depends_on=({"kind": "local", "work_item_id": "li-dep"},),
        ),
    )
    record = _fake().show_issue(issue_id="li-blocked")
    assert {"depends_on_id": "li-dep", "type": EDGE_BLOCKS} in record["dependencies"]


def test_depends_on_non_local_dict_emits_no_edge() -> None:
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-x",
            depends_on=({"kind": "cross-repo", "manifest_ref": "sibling#li-y"},),
        ),
    )
    record = _fake().show_issue(issue_id="li-x")
    assert record["dependencies"] == []


def test_superseded_by_maps_to_supersedes_edge_on_superseding_issue() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-new"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-old", superseded_by="li-new"),
    )
    # The supersedes edge lives on the SUPERSEDING issue (li-new), pointing at
    # the superseded issue (li-old).
    record = _fake().show_issue(issue_id="li-new")
    assert {"depends_on_id": "li-old", "type": EDGE_SUPERSEDES} in record["dependencies"]


def test_read_back_superseded_by_is_none_by_design() -> None:
    """A single record cannot self-report being superseded — reads to None."""
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-new"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-old", superseded_by="li-new"),
    )
    materialized = materialize_work_items(read_work_items(path=_config()))
    assert materialized["li-old"].superseded_by is None


def test_depends_on_non_str_non_dict_entry_emits_no_edge() -> None:
    """A depends_on entry that is neither a string nor a dict is skipped."""
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-x", depends_on=(42,)),
    )
    record = _fake().show_issue(issue_id="li-x")
    assert record["dependencies"] == []


def test_depends_on_local_dict_with_non_string_id_emits_no_edge() -> None:
    """A typed-local dict whose work_item_id is not a string yields no edge."""
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-x",
            depends_on=({"kind": "local", "work_item_id": 99},),
        ),
    )
    record = _fake().show_issue(issue_id="li-x")
    assert record["dependencies"] == []


# --------------------------------------------------------------------------
# Close-in-place semantics.
# --------------------------------------------------------------------------


def test_close_in_place_mutates_existing_record_no_second_record() -> None:
    open_item = _minimal_work_item(id_="li-a", status="open")
    append_work_item(path=_config(), item=open_item)
    audit = AuditRecord(
        verification_timestamp="2026-05-19T02:00:00Z",
        commits=("c1",),
        files_changed=("f1",),
        merge_sha="sha-1",
        pr_number=11,
    )
    closure = _minimal_work_item(
        id_="li-a",
        status="closed",
        resolution="completed",
        reason="shipped",
        audit=audit,
    )
    append_work_item(path=_config(), item=closure)
    # Exactly one record for li-a (in-place mutation, not a second append).
    all_ids = [record["id"] for record in _fake().list_issues()]
    assert all_ids.count("li-a") == 1
    record = _fake().show_issue(issue_id="li-a")
    assert record["status"] == "closed"
    assert record["close_reason"] == "shipped"
    assert "resolution:completed" in record["labels"]
    assert record["metadata"]["audit"]["merge_sha"] == "sha-1"


def test_close_in_place_reads_back_resolution_and_audit() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a", status="open"))
    audit = AuditRecord(
        verification_timestamp="2026-05-19T02:00:00Z",
        commits=(),
        files_changed=(),
        merge_sha="sha-2",
    )
    append_work_item(
        path=_config(),
        item=_minimal_work_item(
            id_="li-a",
            status="closed",
            resolution="spec-revised",
            reason="superseded by spec",
            audit=audit,
        ),
    )
    materialized = materialize_work_items(read_work_items(path=_config()))
    closed = materialized["li-a"]
    assert closed.status == "closed"
    assert closed.resolution == "spec-revised"
    assert closed.reason == "superseded by spec"
    assert closed.audit is not None
    assert closed.audit.merge_sha == "sha-2"


def test_close_in_place_without_resolution_adds_no_resolution_label() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a", status="open"))
    append_work_item(
        path=_config(),
        item=_minimal_work_item(id_="li-a", status="closed", reason="admin close"),
    )
    record = _fake().show_issue(issue_id="li-a")
    assert not any(label.startswith("resolution:") for label in record["labels"])
    assert record["status"] == "closed"


def test_append_born_closed_item_for_absent_id_creates_then_closes() -> None:
    """A fresh record born closed (id not present) is created then closed in place."""
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
            status="closed",
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


# --------------------------------------------------------------------------
# read_work_items returns every issue in the tenant.
# --------------------------------------------------------------------------


def test_read_work_items_returns_every_issue() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a"))
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-b"))
    work_ids = {item.id for item in read_work_items(path=_config())}
    assert work_ids == {"li-a", "li-b"}


# --------------------------------------------------------------------------
# materialize_* — identity reductions kept for API symmetry (R8).
# --------------------------------------------------------------------------


def test_materialize_work_items_is_identity_keyed_by_id() -> None:
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-a"))
    append_work_item(path=_config(), item=_minimal_work_item(id_="li-b"))
    materialized = materialize_work_items(read_work_items(path=_config()))
    assert set(materialized.keys()) == {"li-a", "li-b"}
    assert materialized["li-a"].id == "li-a"


# --------------------------------------------------------------------------
# BeadsMappingError paths — malformed records.
#
# Some malformed shapes (a bad metadata audit object, an invalid label
# enum) can be created through the fake's PUBLIC `create_issue` surface and
# then read back. Others — a non-string `title`, a non-int `priority` — are
# field-shapes the fake never produces, so those are exercised with a small
# stub `BeadsClient` returning a hand-crafted raw record, injected by
# monkeypatching `store.make_beads_client`.
# --------------------------------------------------------------------------


class _StubClient:
    """A read-only stand-in returning a fixed raw record set.

    The store's read path (`read_work_items`) only calls `list_issues`, so
    that is the sole verb implemented; the stub is injected via
    monkeypatching `store.make_beads_client` and never type-checked
    against the full `BeadsClient` protocol.
    """

    def __init__(self, *, records: list[dict[str, object]]) -> None:
        self._records = records

    def list_issues(self) -> list[dict[str, object]]:
        return [dict(record) for record in self._records]


def _install_stub(*, monkeypatch: pytest.MonkeyPatch, records: list[dict[str, object]]) -> None:
    stub = _StubClient(records=records)
    monkeypatch.setattr(
        "livespec_impl_beads.store.make_beads_client",
        lambda *, config: stub,  # noqa: ARG005
    )


def _raw_work_item(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "li-bad",
        "issue_type": "task",
        "status": "open",
        "title": "t",
        "description": "d",
        "priority": 2,
        "assignee": None,
        "created_at": "2026-05-19T00:00:00Z",
        "close_reason": None,
        "spec_id": None,
        "labels": ["origin:freeform"],
        "metadata": {},
        "dependencies": [],
    }
    base.update(overrides)
    return base


def test_missing_origin_label_derives_freeform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A record with no origin label (e.g. raw `bd create`) derives freeform,
    not a mapping error — one unlabeled record must not blind the enumeration."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(labels=[])])
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "freeform"
    assert read_back.gap_id is None


def test_missing_origin_with_gap_id_derives_gap_tied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Origin is derivable: a record carrying a gap-id but no origin label
    reads back as gap-tied."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(labels=["gap-id:G9"])])
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "gap-tied"
    assert read_back.gap_id == "G9"


def test_invalid_origin_label_derives_freeform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognized origin value is treated as malformed and derived from
    gap_id (here absent → freeform), never a hard mapping error."""
    _install_stub(
        monkeypatch=monkeypatch,
        records=[_raw_work_item(labels=["origin:not-a-real-origin"])],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "freeform"


def test_non_string_required_field_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(title=99)])
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "title" in excinfo.value.detail


def test_non_int_priority_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(priority="high")])
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "priority" in excinfo.value.detail


def test_bool_priority_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`True` is an int subclass but must NOT satisfy the integer priority."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(priority=True)])
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "priority" in excinfo.value.detail


def test_non_string_optional_field_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(assignee=7)])
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "assignee" in excinfo.value.detail


def test_optional_field_none_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A null optional field (assignee/description) reads back as None/empty."""
    _install_stub(
        monkeypatch=monkeypatch,
        records=[_raw_work_item(assignee=None, description=None)],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.assignee is None
    assert read_back.description == ""


def test_non_list_labels_treated_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list `labels` value yields no labels → no origin label → derived freeform."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(labels="origin:freeform")])
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "freeform"


def test_non_string_label_entries_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-string entries in the labels list are filtered out, not mapped."""
    _install_stub(
        monkeypatch=monkeypatch,
        records=[_raw_work_item(labels=[123, "origin:freeform", None])],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.origin == "freeform"


def test_non_dict_metadata_treated_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-dict `metadata` value yields no audit (treated as empty object)."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(metadata="nope")])
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is None


def test_non_list_dependencies_treated_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list `dependencies` value yields no depends_on edges."""
    _install_stub(monkeypatch=monkeypatch, records=[_raw_work_item(dependencies="nope")])
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.depends_on == ()


def test_non_dict_dependency_edges_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-dict edge entries (and non-string depends_on_id) are filtered out."""
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(
                dependencies=[
                    "not-a-dict",
                    {"depends_on_id": 7, "type": "blocks"},
                    {"depends_on_id": "li-real", "type": "blocks"},
                    {"depends_on_id": "li-other", "type": "supersedes"},
                ]
            )
        ],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.depends_on == ({"kind": "local", "work_item_id": "li-real"},)


def test_audit_metadata_not_object_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[_raw_work_item(metadata={"audit": "not-an-object"})],
    )
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "audit" in excinfo.value.detail


def test_audit_missing_merge_sha_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(metadata={"audit": {"verification_timestamp": "2026-05-19T00:00:00Z"}})
        ],
    )
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "merge_sha" in excinfo.value.detail


def test_audit_empty_merge_sha_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(
                metadata={
                    "audit": {
                        "verification_timestamp": "2026-05-19T00:00:00Z",
                        "merge_sha": "",
                    }
                }
            )
        ],
    )
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "merge_sha" in excinfo.value.detail


def test_audit_missing_verification_timestamp_raises_mapping_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[_raw_work_item(metadata={"audit": {"merge_sha": "sha"}})],
    )
    with pytest.raises(BeadsMappingError) as excinfo:
        list(read_work_items(path=_config()))
    assert "verification_timestamp" in excinfo.value.detail


def test_audit_non_int_pr_number_reads_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(
                metadata={
                    "audit": {
                        "verification_timestamp": "2026-05-19T00:00:00Z",
                        "merge_sha": "sha",
                        "pr_number": "not-an-int",
                    }
                }
            )
        ],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is not None
    assert read_back.audit.pr_number is None


def test_audit_bool_pr_number_reads_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`True` is an int subclass but must NOT count as a pr_number."""
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(
                metadata={
                    "audit": {
                        "verification_timestamp": "2026-05-19T00:00:00Z",
                        "merge_sha": "sha",
                        "pr_number": True,
                    }
                }
            )
        ],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is not None
    assert read_back.audit.pr_number is None


def test_audit_non_list_commits_reads_as_empty_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(
        monkeypatch=monkeypatch,
        records=[
            _raw_work_item(
                metadata={
                    "audit": {
                        "verification_timestamp": "2026-05-19T00:00:00Z",
                        "merge_sha": "sha",
                        "commits": "not-a-list",
                        "files_changed": [1, "keep", 2],
                    }
                }
            )
        ],
    )
    [read_back] = list(read_work_items(path=_config()))
    assert read_back.audit is not None
    assert read_back.audit.commits == ()
    assert read_back.audit.files_changed == ("keep",)


# --------------------------------------------------------------------------
# Work-item comments — the dispatch-goal rider read.
# --------------------------------------------------------------------------


class _CommentsStubClient:
    """A read-only stand-in returning a fixed raw comment set.

    `read_work_item_comments` only calls `list_comments`, so that is the
    sole verb implemented; injected via monkeypatching
    `store.make_beads_client` (same pattern as `_StubClient`).
    """

    def __init__(self, *, records: list[dict[str, object]]) -> None:
        self._records = records

    def list_comments(self, *, issue_id: str) -> list[dict[str, object]]:
        _ = issue_id
        return [dict(record) for record in self._records]


def test_read_work_item_comments_roundtrip() -> None:
    append_work_item(path=_config(), item=_minimal_work_item())
    _fake().seed_comment(
        issue_id="li-aaa111",
        text="rider one",
        author="operator",
        created_at="2026-06-12T00:00:00Z",
    )
    _fake().seed_comment(issue_id="li-aaa111", text="rider two")
    comments = read_work_item_comments(path=_config(), work_item_id="li-aaa111")
    assert comments == (
        WorkItemComment(text="rider one", author="operator", created_at="2026-06-12T00:00:00Z"),
        WorkItemComment(text="rider two", author=None, created_at=None),
    )


def test_read_work_item_comments_empty_for_uncommented_item() -> None:
    append_work_item(path=_config(), item=_minimal_work_item())
    assert read_work_item_comments(path=_config(), work_item_id="li-aaa111") == ()


def test_read_work_item_comments_skips_unusable_records_fail_soft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A comment without a non-empty string `text` cannot brief anyone and is
    skipped; non-string author/created_at map to None — one malformed comment
    must not blind the whole dispatch-goal read."""
    stub = _CommentsStubClient(
        records=[
            {"text": ""},
            {"text": None},
            {"author": "no-text-at-all"},
            {"text": 42},
            {"text": "kept", "author": 7, "created_at": False},
        ]
    )
    monkeypatch.setattr(
        "livespec_impl_beads.store.make_beads_client",
        lambda *, config: stub,  # noqa: ARG005
    )
    comments = read_work_item_comments(path=_config(), work_item_id="li-any")
    assert comments == (WorkItemComment(text="kept", author=None, created_at=None),)

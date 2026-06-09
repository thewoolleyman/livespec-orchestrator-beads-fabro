"""Beads-backed store primitives for work-items and memos.

This REPLACES the plaintext sibling's append-only JSONL store. The
substrate is a per-repo tenant database on the shared `dolt-server`,
reached through the `BeadsClient` seam (`_beads_client.py`). The public
API is byte-for-byte the SAME six functions the command modules import,
so the wrappers and thin-transport commands do not change:

- `read_work_items(*, path)` — list every issue in the tenant and map
  each onto a `WorkItem` (memos are excluded by the `kind:memo` label).
- `read_memos(*, path)` — the complement: issues carrying `kind:memo`
  mapped onto `Memo`.
- `append_work_item(*, path, item)` — create a new issue, OR, when the
  item carries a `closed` status against an already-present id, mutate it
  in place (close + resolution label + audit metadata). NO second record.
- `append_memo(*, path, memo)` — create a `kind:memo` issue.
- `materialize_work_items(records)` / `materialize_memos(records)` —
  near-identity reductions kept for API symmetry with the plaintext
  store (R8): beads is already one-record-per-id, so there is no
  latest-record-wins fold to perform.

REPURPOSED-PATH: the `path` keyword is retained for call-site
compatibility but is now typed as `StoreConfig` (the connection
descriptor), not a filesystem `Path`. See `types.StoreConfig`.

FIELD MAP (authoritative detail in
dev-tooling/implementation/research/beads-schema-mapping.md):

- id ⇄ id (operator-supplied; prefix == tenant)
- type ⇄ issue_type, status ⇄ status, title/description ⇄ identity
- priority ⇄ priority (0 = highest on both sides)
- assignee ⇄ assignee (first-class)
- captured_at ⇄ created_at
- origin ⇄ label `origin:<value>`; gap_id ⇄ label `gap-id:<id>`
- resolution ⇄ label `resolution:<enum>`
- reason ⇄ close_reason
- audit (whole AuditRecord) ⇄ metadata JSON (lossless)
- spec_commitment_hint ⇄ native `spec_id`
- depends_on (local) ⇄ `blocks` edges; superseded_by ⇄ `supersedes` edge
- epic linkage ⇄ parent-child (`--parent`)

Per SPECIFICATION/constraints.md §"Inherited from livespec" (the
Result-vs-bugs split), EXPECTED backend failures raise the typed
`Beads*Error` classes; a beads record that violates the assumed schema
raises `BeadsMappingError`. Genuine bugs propagate as built-in
exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

from livespec_impl_beads._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    IssueDraft,
    make_beads_client,
)
from livespec_impl_beads.errors import BeadsMappingError
from livespec_impl_beads.types import (
    AuditRecord,
    DependsOnRaw,
    Memo,
    WorkItem,
)

if TYPE_CHECKING:
    from livespec_impl_beads._beads_client import BeadsClient, BeadsRecord
    from livespec_impl_beads.types import StoreConfig

# Label prefixes that carry livespec-side enum/flag fields with no native
# beads home (the bridge-owned label encodings — see the field map).
_LABEL_ORIGIN = "origin:"
_LABEL_GAP_ID = "gap-id:"
_LABEL_RESOLUTION = "resolution:"
_LABEL_KIND = "kind:"
_LABEL_MEMO_STATE = "memo-state:"
_LABEL_MEMO_DISPOSITION = "memo-disposition:"

_MEMO_KIND = "memo"
# Metadata keys carrying livespec fields that ride in the JSON column.
_META_AUDIT = "audit"
_META_MEMO = "memo"

# beads `priority` for memos. Memos carry no livespec priority, so they map
# to the beads schema default (2 = Medium; 0 = highest, 4 = backlog).
_MEMO_DEFAULT_PRIORITY = 2


# --------------------------------------------------------------------------
# Public API — the six functions the command modules import.
# --------------------------------------------------------------------------


def read_work_items(*, path: StoreConfig) -> Iterator[WorkItem]:
    """Stream every (non-memo) issue in the tenant as a WorkItem.

    `path` is the repurposed connection descriptor. Issues carrying the
    `kind:memo` label are excluded (they are memos, surfaced by
    `read_memos`). `depends_on` is populated from each issue's `blocks`
    edges so the existing `next` ranker works UNCHANGED over the
    materialized WorkItems.
    """
    client = make_beads_client(config=path)
    for record in client.list_issues():
        if _is_memo_record(record=record):
            continue
        yield _record_to_work_item(record=record)


def read_memos(*, path: StoreConfig) -> Iterator[Memo]:
    """Stream every `kind:memo` issue in the tenant as a Memo."""
    client = make_beads_client(config=path)
    for record in client.list_issues():
        if not _is_memo_record(record=record):
            continue
        yield _record_to_memo(record=record)


def append_work_item(*, path: StoreConfig, item: WorkItem) -> None:
    """Create a new issue, or close an existing one in place.

    A closure in the JSONL world was a SECOND appended record carrying
    the same id with `status="closed"`. Here that becomes an IN-PLACE
    mutation: when `item.status == "closed"` AND an issue with `item.id`
    already exists in the tenant, we do NOT create a second issue.
    Instead we:

    1. `bd close <id> --reason <reason>` (sets closed status + close_reason),
    2. `bd update <id>` to add the `resolution:<enum>` label, and
    3. write the full `AuditRecord` (lossless) into the metadata JSON
       column.

    Every other append is a fresh `bd create` with the field map applied,
    followed by `bd dep add` edges for `depends_on` (blocks) and
    `superseded_by` (supersedes). This whole semantic shift is contained
    here; the command/skill layer is unaffected.
    """
    client = make_beads_client(config=path)
    if item.status == "closed" and client.exists(issue_id=item.id):
        _close_in_place(client=client, item=item)
        return
    _create_work_item(client=client, item=item)


def append_memo(*, path: StoreConfig, memo: Memo) -> None:
    """Create a `kind:memo` issue carrying the memo's fields."""
    client = make_beads_client(config=path)
    labels = _memo_labels(memo=memo)
    metadata: dict[str, Any] = {_META_MEMO: _memo_metadata(memo=memo)}
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=memo.id,
            issue_type="task",
            title=_memo_title(memo=memo),
            description=memo.text,
            priority=_MEMO_DEFAULT_PRIORITY,
            assignee=None,
            created_at=memo.captured_at,
            labels=labels,
            metadata=metadata,
            spec_id=None,
            parent_id=None,
        )
    )


def materialize_work_items(records: Iterator[WorkItem]) -> dict[str, WorkItem]:
    """Reduce a WorkItem stream to an id-keyed dict.

    Kept for API symmetry with the plaintext store (R8). beads is already
    one-record-per-id (each id maps to exactly one tenant issue), so this
    is an identity collection rather than the plaintext store's
    latest-record-wins fold — but the signature and call sites are
    identical, so the command layer does not branch on substrate.
    """
    return {record.id: record for record in records}


def materialize_memos(records: Iterator[Memo]) -> dict[str, Memo]:
    """Reduce a Memo stream to an id-keyed dict (identity; see R8 note above)."""
    return {record.id: record for record in records}


# --------------------------------------------------------------------------
# Write helpers.
# --------------------------------------------------------------------------


def _create_work_item(*, client: BeadsClient, item: WorkItem) -> None:
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item.id,
            issue_type=item.type,
            title=item.title,
            description=item.description,
            priority=item.priority,
            assignee=item.assignee,
            created_at=item.captured_at,
            labels=_work_item_labels(item=item),
            metadata=_work_item_metadata(item=item),
            spec_id=item.spec_commitment_hint,
            # epic linkage is expressed via the depends_on/supersedes edges
            # below; no create-time --parent is emitted by this bridge.
            parent_id=None,
        )
    )
    _add_dependency_edges(client=client, item=item)
    # An append that arrives already-closed for a NOT-yet-present id (rare:
    # a fresh record born closed) still needs its closed status reflected.
    if item.status == "closed":
        _close_in_place(client=client, item=item)


def _add_dependency_edges(*, client: BeadsClient, item: WorkItem) -> None:
    """Add `blocks` edges for depends_on and a `supersedes` edge if set.

    Each local `depends_on` entry becomes `bd dep add <this> <dep>
    --type blocks` (this issue is blocked by <dep>). A non-null
    `superseded_by` becomes `bd dep add <superseding> <this>
    --type supersedes` (the superseding issue is the edge source, per
    the verified direction in schema-mapping.md item 6).
    """
    for raw in item.depends_on:
        dep_id = _local_depends_on_id(raw=raw)
        if dep_id is not None:
            client.add_dependency(from_id=item.id, to_id=dep_id, edge_type=EDGE_BLOCKS)
    if item.superseded_by is not None:
        client.add_dependency(
            from_id=item.superseded_by,
            to_id=item.id,
            edge_type=EDGE_SUPERSEDES,
        )


def _close_in_place(*, client: BeadsClient, item: WorkItem) -> None:
    """Close an existing issue: bd close + resolution label + audit metadata."""
    client.close_issue(issue_id=item.id, reason=item.reason)
    add_labels: list[str] = []
    if item.resolution is not None:
        add_labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    metadata = _work_item_metadata(item=item)
    client.update_issue(
        issue_id=item.id,
        add_labels=add_labels if add_labels else None,
        metadata=metadata,
    )


def _work_item_labels(*, item: WorkItem) -> list[str]:
    """Build the label set carrying origin / gap-id / resolution."""
    labels: list[str] = [f"{_LABEL_ORIGIN}{item.origin}"]
    if item.gap_id is not None:
        labels.append(f"{_LABEL_GAP_ID}{item.gap_id}")
    if item.resolution is not None:
        labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    return labels


def _work_item_metadata(*, item: WorkItem) -> dict[str, Any]:
    """Build the metadata JSON object: the full AuditRecord (lossless)."""
    metadata: dict[str, Any] = {}
    if item.audit is not None:
        metadata[_META_AUDIT] = _audit_to_dict(audit=item.audit)
    return metadata


def _audit_to_dict(*, audit: AuditRecord) -> dict[str, Any]:
    return {
        "verification_timestamp": audit.verification_timestamp,
        "commits": list(audit.commits),
        "files_changed": list(audit.files_changed),
        "merge_sha": audit.merge_sha,
        "pr_number": audit.pr_number,
    }


def _memo_labels(*, memo: Memo) -> list[str]:
    labels: list[str] = [f"{_LABEL_KIND}{_MEMO_KIND}", f"{_LABEL_MEMO_STATE}{memo.state}"]
    if memo.disposition is not None:
        labels.append(f"{_LABEL_MEMO_DISPOSITION}{memo.disposition}")
    return labels


def _memo_metadata(*, memo: Memo) -> dict[str, Any]:
    return {
        "work_item_id": memo.work_item_id,
        "knowledge_file": memo.knowledge_file,
        "propose_change_topic": memo.propose_change_topic,
    }


def _memo_title(*, memo: Memo) -> str:
    """Derive a short title from the memo text (beads requires a title)."""
    first_line = memo.text.splitlines()[0] if memo.text else memo.id
    return first_line[:80]


# --------------------------------------------------------------------------
# Read helpers — beads record -> WorkItem / Memo.
# --------------------------------------------------------------------------


def _is_memo_record(*, record: BeadsRecord) -> bool:
    return f"{_LABEL_KIND}{_MEMO_KIND}" in _labels_of(record=record)


def _record_to_work_item(*, record: BeadsRecord) -> WorkItem:
    issue_id = _require_str(record=record, key="id")
    labels = _labels_of(record=record)
    metadata = _metadata_of(record=record)
    gap_id = _label_value(labels=labels, prefix=_LABEL_GAP_ID)
    origin = _label_value(labels=labels, prefix=_LABEL_ORIGIN)
    if origin not in ("gap-tied", "freeform"):
        # Origin is derivable: a work item is gap-tied iff it carries a gap_id.
        # Records written outside the capture-work-item path (e.g. raw
        # `bd create`) omit the origin label. Derive it rather than refusing
        # the whole enumeration over a single unlabeled record.
        origin = "gap-tied" if gap_id is not None else "freeform"
    resolution = _label_value(labels=labels, prefix=_LABEL_RESOLUTION)
    audit = _audit_from_metadata(record_id=issue_id, metadata=metadata)
    depends_on = _depends_on_from_edges(record=record)
    return WorkItem(
        id=issue_id,
        type=cast("Any", _require_str(record=record, key="issue_type")),
        status=cast("Any", _require_str(record=record, key="status")),
        title=_require_str(record=record, key="title"),
        description=_optional_str(record=record, key="description") or "",
        origin=cast("Any", origin),
        gap_id=gap_id,
        priority=_require_int(record=record, key="priority"),
        assignee=_optional_str(record=record, key="assignee"),
        depends_on=depends_on,
        captured_at=_require_str(record=record, key="created_at"),
        resolution=cast("Any", resolution),
        reason=_optional_str(record=record, key="close_reason"),
        audit=audit,
        # `supersedes` is stored on the SUPERSEDING issue, so a single
        # record cannot self-report that it was superseded — there is no
        # `superseded_by` edge on this row to read. `superseded_by` does
        # not gate ranker readiness, so None is the safe materialized
        # value; the write path still persists the relationship via the
        # supersedes edge on the superseding issue.
        superseded_by=None,
        spec_commitment_hint=_optional_str(record=record, key="spec_id"),
    )


def _record_to_memo(*, record: BeadsRecord) -> Memo:
    issue_id = _require_str(record=record, key="id")
    labels = _labels_of(record=record)
    metadata = _metadata_of(record=record)
    memo_meta = metadata.get(_META_MEMO)
    memo_meta_dict = cast("dict[str, Any]", memo_meta) if isinstance(memo_meta, dict) else {}
    state = _label_value(labels=labels, prefix=_LABEL_MEMO_STATE)
    if state not in ("untriaged", "dispositioned"):
        raise BeadsMappingError(
            record_id=issue_id,
            detail=f"missing or invalid memo-state label (got {state!r})",
        )
    disposition = _label_value(labels=labels, prefix=_LABEL_MEMO_DISPOSITION)
    return Memo(
        id=issue_id,
        text=_optional_str(record=record, key="description") or "",
        state=cast("Any", state),
        disposition=cast("Any", disposition),
        captured_at=_require_str(record=record, key="created_at"),
        work_item_id=_optional_meta_str(meta=memo_meta_dict, key="work_item_id"),
        knowledge_file=_optional_meta_str(meta=memo_meta_dict, key="knowledge_file"),
        propose_change_topic=_optional_meta_str(meta=memo_meta_dict, key="propose_change_topic"),
    )


def _depends_on_from_edges(*, record: BeadsRecord) -> tuple[DependsOnRaw, ...]:
    """Reconstruct `depends_on` from the `blocks` edges as v072 typed-dicts.

    Each `blocks` edge `{depends_on_id, type:"blocks"}` means this issue
    is blocked by `depends_on_id`, which is exactly the livespec
    `depends_on` semantics. beads `blocks` edges are intra-tenant, so the
    only relationship ever materialized is the `local` kind (cross-tenant
    kinds were never representable as edges). Each edge is emitted in the
    v072 typed-dict form `{"kind": "local", "work_item_id": <dep_id>}`
    required by livespec's `DependsOnEntry` schema and the doctor
    `depends_on-ref-wellformedness` / `no-orphan-dependency` integrity
    checks — the legacy bare-string form fails wellformedness on every
    dependency edge. `_cross_repo.parse_entry` maps this typed-dict to
    `LocalDependency`, so the `next` ranker stays unchanged.
    """
    deps: list[DependsOnRaw] = []
    for edge in _edges_of(record=record):
        if edge.get("type") == EDGE_BLOCKS:
            dep_id = edge.get("depends_on_id")
            if isinstance(dep_id, str):
                deps.append({"kind": "local", "work_item_id": dep_id})
    return tuple(deps)


def _audit_from_metadata(
    *,
    record_id: str,
    metadata: dict[str, Any],
) -> AuditRecord | None:
    raw = metadata.get(_META_AUDIT)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BeadsMappingError(
            record_id=record_id,
            detail="metadata 'audit' is not a JSON object",
        )
    audit_dict = cast("dict[str, Any]", raw)
    merge_sha = audit_dict.get("merge_sha")
    if not isinstance(merge_sha, str) or merge_sha == "":
        raise BeadsMappingError(
            record_id=record_id,
            detail="metadata audit 'merge_sha' must be a non-empty string",
        )
    pr_number_raw = audit_dict.get("pr_number")
    pr_number = (
        pr_number_raw
        if isinstance(pr_number_raw, int) and not isinstance(pr_number_raw, bool)
        else None
    )
    return AuditRecord(
        verification_timestamp=_require_meta_str(
            record_id=record_id, meta=audit_dict, key="verification_timestamp"
        ),
        commits=_str_tuple(value=audit_dict.get("commits")),
        files_changed=_str_tuple(value=audit_dict.get("files_changed")),
        merge_sha=merge_sha,
        pr_number=pr_number,
    )


# --------------------------------------------------------------------------
# Small typed accessors for the loosely-typed beads record dict.
# --------------------------------------------------------------------------


def _labels_of(*, record: BeadsRecord) -> list[str]:
    raw = record.get("labels")
    if not isinstance(raw, list):
        return []
    items = cast("list[Any]", raw)
    return [label for label in items if isinstance(label, str)]


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    if isinstance(raw, dict):
        return cast("dict[str, Any]", raw)
    return {}


def _edges_of(*, record: BeadsRecord) -> list[dict[str, Any]]:
    raw = record.get("dependencies")
    if not isinstance(raw, list):
        return []
    items = cast("list[Any]", raw)
    return [edge for edge in items if isinstance(edge, dict)]


def _label_value(*, labels: list[str], prefix: str) -> str | None:
    """Return the value of the single label carrying `prefix`, or None."""
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _local_depends_on_id(*, raw: object) -> str | None:
    """Extract the local work-item id from a depends_on entry, or None.

    Accepts both the bare-string form and the typed-dict form
    `{"kind":"local","work_item_id":"<id>"}`. Non-local kinds have no
    beads home (intra-tenant edges only) and are skipped.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        entry = cast("dict[str, Any]", raw)
        if entry.get("kind") == "local":
            work_item_id = entry.get("work_item_id")
            if isinstance(work_item_id, str):
                return work_item_id
    return None


def _require_str(*, record: BeadsRecord, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise BeadsMappingError(
            record_id=str(record.get("id", "<unknown>")),
            detail=f"field {key!r} must be a string (got {type(value).__name__})",
        )
    return value


def _optional_str(*, record: BeadsRecord, key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BeadsMappingError(
            record_id=str(record.get("id", "<unknown>")),
            detail=f"field {key!r} must be a string or null (got {type(value).__name__})",
        )
    return value


def _require_int(*, record: BeadsRecord, key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BeadsMappingError(
            record_id=str(record.get("id", "<unknown>")),
            detail=f"field {key!r} must be an integer (got {type(value).__name__})",
        )
    return value


def _require_meta_str(*, record_id: str, meta: dict[str, Any], key: str) -> str:
    value = meta.get(key)
    if not isinstance(value, str):
        raise BeadsMappingError(
            record_id=record_id,
            detail=f"metadata field {key!r} must be a string (got {type(value).__name__})",
        )
    return value


def _optional_meta_str(*, meta: dict[str, Any], key: str) -> str | None:
    value = meta.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value


def _str_tuple(*, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = cast("list[Any]", value)
    return tuple(item for item in items if isinstance(item, str))

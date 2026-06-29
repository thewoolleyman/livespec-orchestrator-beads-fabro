"""Beads-backed store primitives for work-items.

This REPLACES the plaintext sibling's append-only JSONL store. The
substrate is a per-repo tenant database on the shared `dolt-server`,
reached through the `BeadsClient` seam (`_beads_client.py`). The public
API is byte-for-byte the SAME functions the command modules import, so
the wrappers and thin-transport commands do not change:

- `read_work_items(*, path)` — list every issue in the tenant and map
  each onto a `WorkItem`.
- `append_work_item(*, path, item)` — create a new issue (2-step: `bd
  create` + `bd update --status <state>`), OR, when the item carries a
  `done` status against an already-present id, mutate it in place (close +
  resolution label + audit metadata). NO second record.
- `register_custom_statuses(*, path)` — per-tenant bootstrap registering
  the 5 custom livespec statuses (idempotent).

`materialize_work_items` is no longer defined here: the canonical
keyword-only head reduction is the SHARED
`livespec_runtime.work_items.reduce.materialize_work_items`, re-exported
below for the command-layer call sites. beads is inherently
one-record-per-id (every issue's `supersedes` is `None`), so the
canonical reduction is its degenerate identity-collection case and
produces the SAME id-keyed dict the local near-identity reduction did.

`BeadsWorkItemStore` is the thin conformance facade satisfying the
shared `livespec_runtime.work_items.store.WorkItemStore` Protocol over
the EXISTING `read_work_items` / `append_work_item` free functions.
Backend I/O — the `_record_to_work_item` field map, label/edge/metadata
mapping, and the comments sidecar (`read_work_item_comments` /
`WorkItemComment`, deliberately NOT part of the shared contract) — stays
LOCAL.

REPURPOSED-PATH: the `path` keyword is retained for call-site
compatibility but is now typed as `StoreConfig` (the connection
descriptor), not a filesystem `Path`. See `types.StoreConfig`.

FIELD MAP (authoritative detail in
dev-tooling/implementation/research/beads-schema-mapping.md):

- id ⇄ id (operator-supplied; prefix is the decoupled issue-prefix, e.g. bd-ib)
- type ⇄ issue_type, title/description ⇄ identity
- status ⇄ status: the 5 custom states + `blocked` map by the SAME name;
  only `done` ⇄ `closed` is translated (the one adapter name-mapping).
- rank ⇄ `metadata.rank` (sole ordering authority; a rank-less legacy
  issue reads back the bottom sentinel). `priority` is REMOVED as a logical
  field — the native `priority` column survives harmlessly but is no longer
  read into the materialized record.
- assignee ⇄ assignee (first-class)
- captured_at ⇄ created_at
- origin ⇄ label `origin:<value>`; gap_id ⇄ label `gap-id:<id>`
- resolution ⇄ label `resolution:<enum>`
- admission_policy / acceptance_policy / blocked_reason ⇄ labels
  `admission:<v>` / `acceptance:<v>` / `blocked-reason:<v>` (absent → None)
- reason ⇄ close_reason
- audit (whole AuditRecord) ⇄ metadata JSON (lossless)
- spec_commitment_hint ⇄ native `spec_id`
- depends_on (local) ⇄ `blocks` edges; superseded_by ⇄ `supersedes` edge
- epic linkage ⇄ parent-child (`--parent`)

Per SPECIFICATION/constraints.md (the
Result-vs-bugs split), EXPECTED backend failures raise the typed
`Beads*Error` classes; a beads record that violates the assumed schema
raises `BeadsMappingError`. Genuine bugs propagate as built-in
exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_runtime.work_items.rank import BOTTOM_SENTINEL
from livespec_runtime.work_items.reduce import materialize_work_items
from livespec_runtime.work_items.store import WorkItemStore

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError
from livespec_orchestrator_beads_fabro.types import (
    AuditRecord,
    DependsOnRaw,
    WorkItem,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__ = [
    "BeadsWorkItemStore",
    "WorkItemComment",
    "append_work_item",
    "materialize_work_items",
    "read_work_item_comments",
    "read_work_items",
    "register_custom_statuses",
]

# Label prefixes that carry livespec-side enum/flag fields with no native
# beads home (the bridge-owned label encodings — see the field map).
_LABEL_ORIGIN = "origin:"
_LABEL_GAP_ID = "gap-id:"
_LABEL_RESOLUTION = "resolution:"
_LABEL_ADMISSION = "admission:"
_LABEL_ACCEPTANCE = "acceptance:"
_LABEL_BLOCKED_REASON = "blocked-reason:"

# Metadata keys carrying livespec fields that ride in the JSON column.
_META_AUDIT = "audit"
_META_NON_LOCAL_DEPENDS_ON = "non_local_depends_on"
_META_RANK = "rank"

# The one adapter status name-mapping: livespec `done` is beads' built-in
# `closed` (native closure: `closed_at`, `bd close`, done-hiding). Every
# other livespec state maps to a beads status of the SAME name (5 custom +
# the reused built-in `blocked`), so only this pair needs translation.
_LIVESPEC_DONE = "done"
_BEADS_CLOSED = "closed"


def _beads_status_for(*, status: str) -> str:
    """Map a livespec status onto its beads status (`done` → `closed`)."""
    return _BEADS_CLOSED if status == _LIVESPEC_DONE else status


def _livespec_status_for(*, status: str) -> str:
    """Map a beads status onto its livespec status (`closed` → `done`)."""
    return _LIVESPEC_DONE if status == _BEADS_CLOSED else status


def _rank_from_metadata(*, metadata: dict[str, Any]) -> str:
    """Read `rank` from the metadata JSON, substituting the bottom sentinel.

    A legacy issue written before `rank` existed has no `metadata.rank`; it
    reads back through `rank.BOTTOM_SENTINEL` so it sorts strictly after
    every real key WITHOUT making the domain `WorkItem.rank` nullable.
    """
    value = metadata.get(_META_RANK)
    if isinstance(value, str) and value != "":
        return value
    return BOTTOM_SENTINEL


# --------------------------------------------------------------------------
# Public API — the functions the command modules import.
# --------------------------------------------------------------------------


def read_work_items(*, path: StoreConfig) -> Iterator[WorkItem]:
    """Stream every issue in the tenant as a WorkItem.

    `path` is the repurposed connection descriptor. `depends_on` is
    populated from each issue's `blocks` edges so the existing `next`
    ranker works UNCHANGED over the materialized WorkItems.
    """
    client = make_beads_client(config=path)
    for record in client.list_issues():
        yield _record_to_work_item(record=record)


@dataclass(frozen=True, kw_only=True)
class WorkItemComment:
    """One comment on a work-item, mapped from a `bd comments` record.

    Comments are operator RIDERS appended to an item after filing (e.g.
    pre-authorizations, scope amendments). They are deliberately NOT a
    `WorkItem` field — the work-item record schema is codified by
    SPECIFICATION/contracts.md and comments are a beads-native sidecar,
    read on demand by the Dispatcher to fold into the dispatch goal.
    """

    text: str
    author: str | None
    created_at: str | None


def read_work_item_comments(
    *,
    path: StoreConfig,
    work_item_id: str,
) -> tuple[WorkItemComment, ...]:
    """Read the comments on one work-item, oldest-first.

    `bd show` carries only `comment_count` (never bodies), so this is a
    dedicated `bd comments <id> --json` read via the client seam.
    Fail-soft per record: an entry without a non-empty string `text` is
    skipped (it cannot brief anyone), and non-string `author` /
    `created_at` values map to None — one malformed comment must not
    blind the whole read.
    """
    client = make_beads_client(config=path)
    comments: list[WorkItemComment] = []
    for record in client.list_comments(issue_id=work_item_id):
        text_raw: object = record.get("text")
        if not isinstance(text_raw, str) or text_raw == "":
            continue
        comments.append(
            WorkItemComment(
                text=text_raw,
                author=_comment_field_str(value=record.get("author")),
                created_at=_comment_field_str(value=record.get("created_at")),
            )
        )
    return tuple(comments)


def _comment_field_str(*, value: object) -> str | None:
    """Map a raw comment field onto `str | None` (non-strings drop to None).

    Deliberately laxer than the issue-record `_optional_str` (which
    RAISES on a non-string): a malformed comment sidecar field fails
    soft, because a rider read must never blind the dispatch.
    """
    return value if isinstance(value, str) else None


def append_work_item(*, path: StoreConfig, item: WorkItem) -> None:
    """Create a new issue, or close an existing one in place.

    A closure in the JSONL world was a SECOND appended record carrying
    the same id with `status="done"`. Here that becomes an IN-PLACE
    mutation: when `item.status == "done"` AND an issue with `item.id`
    already exists in the tenant, we do NOT create a second issue.
    Instead we:

    1. `bd close <id> --reason <reason>` (sets beads `closed` ≡ livespec
       `done`, plus `close_reason`),
    2. `bd update <id>` to add the `resolution:<enum>` label, and
    3. write the full `AuditRecord` (lossless) into the metadata JSON
       column.

    Every other append is a fresh 2-step `bd create` (lands `open`) +
    `bd update --status <state>` (the custom livespec status), followed by
    `bd dep add` edges for `depends_on` (blocks) and `superseded_by`
    (supersedes). This whole semantic shift is contained here; the
    command/skill layer is unaffected.
    """
    client = make_beads_client(config=path)
    if item.status == _LIVESPEC_DONE and client.exists(issue_id=item.id):
        _close_in_place(client=client, item=item)
        return
    _create_work_item(client=client, item=item)


def register_custom_statuses(*, path: StoreConfig) -> None:
    """Provision the tenant's five custom livespec statuses (idempotent).

    A per-tenant bootstrap step: `bd create` cannot land directly in a
    custom status, so the 2-step `append_work_item` path depends on the
    custom statuses already being registered on the tenant. Delegates to
    the client seam's `register_custom_statuses` verb (a real
    `bd config set status.custom` against the live tenant; a recorded no-op
    against the in-memory fake).
    """
    client = make_beads_client(config=path)
    client.register_custom_statuses()


class BeadsWorkItemStore:
    """Thin `WorkItemStore` conformance facade over the store free functions.

    The shared `livespec_runtime.work_items.store.WorkItemStore` Protocol
    is the substrate-neutral contract — a stream of `WorkItem` out, one
    `WorkItem` in — that the canonical reducer and the `next` ranker
    depend on. This facade satisfies it by delegating to the EXISTING
    `read_work_items` / `append_work_item` free functions over the
    resolved beads connection descriptor; it adds no new backend
    behavior. The module-level `_: type[WorkItemStore]` assertion below
    is the pyright-checked conformance pin.
    """

    def __init__(self, *, config: StoreConfig) -> None:
        self._config = config

    def read_work_items(self) -> Iterator[WorkItem]:
        """Stream every WorkItem in the tenant (delegates to the free function)."""
        return read_work_items(path=self._config)

    def append_work_item(self, *, item: WorkItem) -> None:
        """Add one WorkItem to the tenant (delegates to the free function)."""
        append_work_item(path=self._config, item=item)


# A pyright-checked structural-conformance pin: `BeadsWorkItemStore`
# satisfies the shared `WorkItemStore` Protocol. If the facade ever
# drifts from the contract, strict typechecking fails here.
_: type[WorkItemStore] = BeadsWorkItemStore


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
            # `priority` is the beads-native column only; the logical model
            # dropped it for `rank` (persisted in metadata), so the draft
            # uses IssueDraft's neutral default rather than sourcing it here.
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
    # `bd create` cannot land directly in a custom status, so every initial
    # write is 2-step: the create above lands `open`, then the status is set
    # to the real livespec state. A record born already-`done` takes the
    # in-place close path instead (which sets beads `closed`).
    if item.status == _LIVESPEC_DONE:
        _close_in_place(client=client, item=item)
    else:
        client.update_issue(issue_id=item.id, status=_beads_status_for(status=item.status))


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
    """Build the label set carrying origin / gap-id / resolution / policy fields.

    The `admission_policy` / `acceptance_policy` / `blocked_reason` fields
    follow the blessed optional-on-read pattern: a `None` value writes NO
    label (it reads back `None` = inherit / system default), so only a set
    policy materializes a `admission:` / `acceptance:` / `blocked-reason:`
    label.
    """
    labels: list[str] = [f"{_LABEL_ORIGIN}{item.origin}"]
    if item.gap_id is not None:
        labels.append(f"{_LABEL_GAP_ID}{item.gap_id}")
    if item.resolution is not None:
        labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    if item.admission_policy is not None:
        labels.append(f"{_LABEL_ADMISSION}{item.admission_policy}")
    if item.acceptance_policy is not None:
        labels.append(f"{_LABEL_ACCEPTANCE}{item.acceptance_policy}")
    if item.blocked_reason is not None:
        labels.append(f"{_LABEL_BLOCKED_REASON}{item.blocked_reason}")
    return labels


def _work_item_metadata(*, item: WorkItem) -> dict[str, Any]:
    """Build the metadata JSON object: rank + the full AuditRecord + non-local depends_on.

    `rank` is the sole ordering authority and a strictly-required non-null
    field, so it is ALWAYS written into `metadata.rank` (both on create and
    on the in-place close, which re-writes metadata).
    """
    metadata: dict[str, Any] = {_META_RANK: item.rank}
    if item.audit is not None:
        metadata[_META_AUDIT] = _audit_to_dict(audit=item.audit)
    non_local = _non_local_depends_on_list(depends_on=item.depends_on)
    if non_local:
        metadata[_META_NON_LOCAL_DEPENDS_ON] = non_local
    return metadata


def _non_local_depends_on_list(*, depends_on: tuple[DependsOnRaw, ...]) -> list[dict[str, Any]]:
    """Collect non-local depends_on entries for metadata storage.

    Local entries (bare strings or {"kind": "local", ...} dicts) are stored as
    beads blocks edges. Non-local dict entries have no edge home and ride in
    metadata so cross-repo DAGs survive the round-trip.
    """
    result: list[dict[str, Any]] = []
    for raw in depends_on:
        if isinstance(raw, dict) and raw.get("kind") != "local":
            result.append(dict(raw))
    return result


def _audit_to_dict(*, audit: AuditRecord) -> dict[str, Any]:
    return {
        "verification_timestamp": audit.verification_timestamp,
        "commits": list(audit.commits),
        "files_changed": list(audit.files_changed),
        "merge_sha": audit.merge_sha,
        "pr_number": audit.pr_number,
    }


# --------------------------------------------------------------------------
# Read helpers — beads record -> WorkItem.
# --------------------------------------------------------------------------


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
    depends_on = _depends_on_from_edges(record=record, metadata=metadata)
    return WorkItem(
        id=issue_id,
        type=cast("Any", _require_str(record=record, key="issue_type")),
        # Map the beads status back to its livespec name (`closed` → `done`);
        # the 5 custom statuses + the reused `blocked` pass through.
        status=cast("Any", _livespec_status_for(status=_require_str(record=record, key="status"))),
        title=_require_str(record=record, key="title"),
        description=_optional_str(record=record, key="description") or "",
        origin=cast("Any", origin),
        gap_id=gap_id,
        # `rank` is read from `metadata.rank`; a legacy rank-less issue reads
        # back the bottom sentinel (the native `priority` column is no longer
        # mapped into the logical record).
        rank=_rank_from_metadata(metadata=metadata),
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
        # Policy fields read back from their labels; an absent label is the
        # blessed `None` (inherit / system default).
        admission_policy=cast("Any", _label_value(labels=labels, prefix=_LABEL_ADMISSION)),
        acceptance_policy=cast("Any", _label_value(labels=labels, prefix=_LABEL_ACCEPTANCE)),
        blocked_reason=cast("Any", _label_value(labels=labels, prefix=_LABEL_BLOCKED_REASON)),
    )


def _depends_on_from_edges(
    *,
    record: BeadsRecord,
    metadata: dict[str, Any],
) -> tuple[DependsOnRaw, ...]:
    """Reconstruct `depends_on` from blocks edges (local) and metadata (non-local).

    Each `blocks` edge `{depends_on_id, type:"blocks"}` means this issue
    is blocked by `depends_on_id`, which is exactly the livespec
    `depends_on` semantics. beads `blocks` edges are intra-tenant, so the
    only relationship ever materialized from edges is the `local` kind.
    Each edge is emitted in the v072 typed-dict form
    `{"kind": "local", "work_item_id": <dep_id>}` required by livespec's
    `DependsOnEntry` schema and the doctor checks.

    Non-local entries (sibling_work_item, pull_request, branch) have no
    edge home; they are persisted in `metadata[_META_NON_LOCAL_DEPENDS_ON]`
    by the write path and reconstructed here so cross-repo DAGs survive.
    """
    deps: list[DependsOnRaw] = []
    for edge in _edges_of(record=record):
        if edge.get("type") == EDGE_BLOCKS:
            dep_id = edge.get("depends_on_id")
            if isinstance(dep_id, str):
                deps.append({"kind": "local", "work_item_id": dep_id})
    non_local_raw = metadata.get(_META_NON_LOCAL_DEPENDS_ON)
    if isinstance(non_local_raw, list):
        deps.extend(cast("list[DependsOnRaw]", non_local_raw))
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


def _require_meta_str(*, record_id: str, meta: dict[str, Any], key: str) -> str:
    value = meta.get(key)
    if not isinstance(value, str):
        raise BeadsMappingError(
            record_id=record_id,
            detail=f"metadata field {key!r} must be a string (got {type(value).__name__})",
        )
    return value


def _str_tuple(*, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = cast("list[Any]", value)
    return tuple(item for item in items if isinstance(item, str))

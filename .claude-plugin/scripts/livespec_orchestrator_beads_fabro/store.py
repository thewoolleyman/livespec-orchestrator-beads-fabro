"""Beads-backed read facade and public store re-exports.

Mutation entry points live in `_store_mutations`; this module keeps the
record-to-WorkItem read map, comment sidecar reads, native-priority helper,
and the `BeadsWorkItemStore` facade while preserving the original public API.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

from livespec_runtime.work_items.reduce import materialize_work_items

from livespec_orchestrator_beads_fabro._beads_client import EDGE_BLOCKS, make_beads_client
from livespec_orchestrator_beads_fabro._store_beads_store import BeadsWorkItemStore
from livespec_orchestrator_beads_fabro._store_comments import (
    WorkItemComment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro._store_mutations import (
    append_work_item,
    register_custom_statuses,
    update_work_item_policy,
    update_work_item_rank,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro._store_native_priorities import (
    read_work_item_native_priorities,
)
from livespec_orchestrator_beads_fabro._store_rank import rank_from_metadata
from livespec_orchestrator_beads_fabro._store_statuses import (
    ALLOWED_BEADS_STATUSES,
    livespec_status_for,
)
from livespec_orchestrator_beads_fabro.errors import BeadsMappingError
from livespec_orchestrator_beads_fabro.types import (
    AuditRecord,
    DependsOnRaw,
    WorkItem,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ALLOWED_BEADS_STATUSES",
    "BeadsWorkItemStore",
    "WorkItemComment",
    "append_work_item",
    "materialize_work_items",
    "read_work_item_comments",
    "read_work_item_native_priorities",
    "read_work_items",
    "register_custom_statuses",
    "update_work_item_policy",
    "update_work_item_rank",
    "update_work_item_status",
]

# Label prefixes that carry livespec-side enum/flag fields with no native
# beads home (the bridge-owned label encodings — see the field map).
_LABEL_ORIGIN = "origin:"
_LABEL_GAP_ID = "gap-id:"
_LABEL_RESOLUTION = "resolution:"
_LABEL_ADMISSION = "admission:"
_LABEL_ACCEPTANCE = "acceptance:"
_LABEL_BLOCKED_REASON = "blocked-reason:"
_LABEL_FACTORY_SAFETY = "factory-safety:"

# Metadata keys carrying livespec fields that ride in the JSON column.
_META_AUDIT = "audit"
_META_ACCEPTANCE_CRITERIA = "acceptance_criteria"
_META_NON_LOCAL_DEPENDS_ON = "non_local_depends_on"
_META_NOTES = "notes"

_LEGACY_HOST_MARKER_RE = re.compile(r"(?<![\w-])host[-_]only(?![\w-])", re.IGNORECASE)

# The one adapter status name-mapping: livespec `done` is beads' built-in
# `closed` (native closure: `closed_at`, `bd close`, done-hiding). Every
# other livespec state maps to a beads status of the SAME name (5 custom +
# the reused built-in `blocked`), so only this pair needs translation.


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
    content_fields = {**metadata, **record}
    title = _require_str(record=record, key="title")
    description = _optional_str(record=record, key="description") or ""
    factory_safety = _factory_safety_from_labels_or_legacy(
        labels=labels,
        title=title,
        description=description,
    )
    return WorkItem(
        id=issue_id,
        type=cast("Any", _require_str(record=record, key="issue_type")),
        # Map the beads status back to its livespec name (`closed` → `done`);
        # the 5 custom statuses + the reused `blocked` pass through.
        status=cast("Any", livespec_status_for(status=_require_str(record=record, key="status"))),
        title=title,
        description=description,
        origin=cast("Any", origin),
        gap_id=gap_id,
        # `rank` is read from `metadata.rank`; a legacy rank-less issue reads
        # back the bottom sentinel (the native `priority` column is no longer
        # mapped into the logical record).
        rank=rank_from_metadata(metadata=metadata),
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
        acceptance_criteria=_optional_str(record=content_fields, key=_META_ACCEPTANCE_CRITERIA),
        notes=_optional_str(record=content_fields, key=_META_NOTES),
        # Policy fields read back from their labels; an absent label is the
        # blessed `None` (inherit / system default).
        admission_policy=cast("Any", _label_value(labels=labels, prefix=_LABEL_ADMISSION)),
        acceptance_policy=cast("Any", _label_value(labels=labels, prefix=_LABEL_ACCEPTANCE)),
        blocked_reason=cast("Any", _label_value(labels=labels, prefix=_LABEL_BLOCKED_REASON)),
        factory_safety=cast("Any", factory_safety),
    )


def _factory_safety_from_labels_or_legacy(
    *,
    labels: list[str],
    title: str,
    description: str,
) -> str | None:
    explicit = _label_value(labels=labels, prefix=_LABEL_FACTORY_SAFETY)
    if explicit is not None:
        return explicit
    if _LEGACY_HOST_MARKER_RE.search(f"{title}\n{description}") is not None:
        return "mutates-host-machinery"
    return None


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

"""Metadata construction helpers for beads-backed work-item mutations."""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.types import AuditRecord, DependsOnRaw, WorkItem

__all__: list[str] = [
    "rank_metadata",
    "work_item_metadata",
    "work_item_metadata_preserving_existing",
]

_META_AUDIT = "audit"
_META_NON_LOCAL_DEPENDS_ON = "non_local_depends_on"
_META_RANK = "rank"


def work_item_metadata(*, item: WorkItem) -> dict[str, Any]:
    """Build metadata: rank + AuditRecord + non-local depends_on.

    `rank` is the sole ordering authority and a strictly-required non-null
    field, so it is ALWAYS written into `metadata.rank` (both on create and
    on the in-place close, which re-writes metadata).

    Acceptance criteria and notes are intentionally absent here. They are
    top-level beads fields so `bd show` and dispatcher reads share one source
    of truth; legacy metadata copies remain read-only fallback in `store.py`.
    """
    metadata: dict[str, Any] = {_META_RANK: item.rank}
    if item.audit is not None:
        metadata[_META_AUDIT] = _audit_to_dict(audit=item.audit)
    non_local = _non_local_depends_on_list(depends_on=item.depends_on)
    if non_local:
        metadata[_META_NON_LOCAL_DEPENDS_ON] = non_local
    return metadata


def rank_metadata(*, existing_metadata: dict[str, Any], rank: str) -> dict[str, Any]:
    """Overlay a real order key onto existing metadata, retaining every other key.

    The rank half of the ledger-normalization adoption write, which holds an id
    and a freshly generated key but no `WorkItem` to rebuild metadata from. It
    therefore overlays `rank` alone: `audit` and every unmodeled key survive
    verbatim, which matters because `bd update --metadata` replaces a nested
    object wholesale with whatever the payload carries.
    """
    metadata = dict(existing_metadata)
    metadata[_META_RANK] = rank
    return metadata


def work_item_metadata_preserving_existing(
    *,
    existing_metadata: dict[str, Any],
    item: WorkItem,
) -> dict[str, Any]:
    """Overlay modeled metadata fields while retaining unmodeled keys."""
    metadata = dict(existing_metadata)
    updated = work_item_metadata(item=item)
    existing_audit = metadata.get(_META_AUDIT)
    updated_audit = updated.get(_META_AUDIT)
    metadata.update(updated)
    if isinstance(existing_audit, dict) and isinstance(updated_audit, dict):
        audit = dict(cast("dict[str, Any]", existing_audit))
        audit.update(cast("dict[str, Any]", updated_audit))
        metadata[_META_AUDIT] = audit
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

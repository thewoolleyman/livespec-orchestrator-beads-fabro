"""Migration helpers for retiring legacy metadata content fields."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "backfill_native_content_fields",
]

_META_ACCEPTANCE_CRITERIA = "acceptance_criteria"
_META_NOTES = "notes"


def backfill_native_content_fields(*, path: StoreConfig) -> int:
    """Move legacy metadata acceptance/notes into native beads fields.

    The chosen design makes native `acceptance_criteria` and `notes` the
    single source for human `bd show` and factory dispatch. The native backfill
    is idempotent: a native field is written only when the record carries none.

    THE RETIRED METADATA COPIES ARE NOT REMOVED, though the payload below is
    built to remove them (bd-ib-anwf). It sends the metadata object without the
    two legacy keys, and `bd update --metadata` MERGES top-level keys: a key
    the payload omits is left as it is. So every migrated record keeps its
    stale copy, and each later run counts that record again, because the copy
    it tests for is still there. Its writes change nothing on those runs.
    Removing a key takes `bd update --unset-metadata <key>`, which this client
    does not send.
    """
    client = make_beads_client(config=path)
    changed = 0
    for record in client.list_issues():
        issue_id = record.get("id")
        if not isinstance(issue_id, str):
            continue
        raw_metadata = record.get("metadata")
        if not isinstance(raw_metadata, dict):
            continue
        metadata = cast("dict[str, Any]", raw_metadata)
        next_metadata = dict(metadata)
        legacy_acceptance = next_metadata.pop(_META_ACCEPTANCE_CRITERIA, None)
        legacy_notes = next_metadata.pop(_META_NOTES, None)
        acceptance_update = _legacy_value(
            record=record,
            key=_META_ACCEPTANCE_CRITERIA,
            value=legacy_acceptance,
        )
        notes_update = _legacy_value(record=record, key=_META_NOTES, value=legacy_notes)
        if next_metadata == metadata and acceptance_update is None and notes_update is None:
            continue
        client.update_issue(
            issue_id=issue_id,
            metadata=next_metadata,
            acceptance_criteria=acceptance_update,
            notes=notes_update,
        )
        changed += 1
    return changed


def _legacy_value(*, record: dict[str, Any], key: str, value: object) -> str | None:
    if key in record or not isinstance(value, str):
        return None
    return value

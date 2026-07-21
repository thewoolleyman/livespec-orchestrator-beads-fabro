"""Narrow raw read of the intake-triage marker and the beads-native priority.

`WorkItem` carries neither of the two signals the un-triaged-backlog
attention lane needs. Labels are decoded into named fields by
`store._record_to_work_item`, so an unrecognized marker label is dropped on
the floor; and the logical `priority` field was REMOVED in favor of `rank`
as the sole ordering authority, so the native column never reaches the
materialized record. This module is the narrow raw read for exactly that
lane, mirroring `_store_native_priorities` (the other narrow raw read).

The two signals:

- `intake:triaged` — the marker `intake_dor.apply_intake_dor` stamps for
  EVERY verdict it routes. Its presence is the only observable evidence
  that the intake Definition-of-Ready gate saw an item at all, which is
  what separates a deliberately-parked epic (gated, routed to `backlog`)
  from an item filed through the wrong door that will never move. A
  maintainer may also set it by hand to dismiss a parked item from the
  lane.
- `priority` — the beads-native column (lower = more urgent). It is
  decorative for bridge-written records (`append_work_item` always writes
  the neutral default), but a record filed OUTSIDE the bridge with a raw
  `bd create` carries a real P0/P1, and that population is precisely the
  one this lane reports on. It is the only absolute urgency signal such a
  record has — `rank` is a relative ordering key with no urgency tier.

Reads here are FAIL-SOFT, per the reader discipline the needs-attention
surface follows: a record missing a required string field is skipped rather
than failing the whole enumeration, and a missing or non-integer priority
reads back as `None` (no urgency signal). The strict mapping path that
surfaces a malformed record as a `BeadsMappingError` stays
`store.read_work_items`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_statuses import livespec_status_for

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "INTAKE_TRIAGED_LABEL",
    "IntakeTriageRecord",
    "read_intake_triage_records",
]

# The marker label the intake Definition-of-Ready gate stamps for every
# verdict it routes. Defined HERE rather than in `intake_dor` because the
# read side must not import the write side: `intake_dor` already imports
# `store`, so the reverse edge would close an import cycle.
INTAKE_TRIAGED_LABEL = "intake:triaged"


@dataclass(frozen=True, slots=True, kw_only=True)
class IntakeTriageRecord:
    """One tenant record reduced to the intake-triage lane's raw signals.

    `status` is the LIVESPEC status name (beads' `closed` already mapped
    back to `done`), so callers compare against the same vocabulary
    `WorkItem.status` uses. `priority` is `None` when the record carries no
    usable native priority.
    """

    id: str
    title: str
    status: str
    priority: int | None
    triaged: bool


def read_intake_triage_records(*, path: StoreConfig) -> tuple[IntakeTriageRecord, ...]:
    """Return the intake-triage signals for every issue in the tenant."""
    client = make_beads_client(config=path)
    reduced = (_triage_record(record=record) for record in client.list_issues())
    return tuple(record for record in reduced if record is not None)


def _triage_record(*, record: BeadsRecord) -> IntakeTriageRecord | None:
    """Reduce one raw beads record, or None when it is unusable."""
    issue_id = _optional_str(record=record, key="id")
    title = _optional_str(record=record, key="title")
    status = _optional_str(record=record, key="status")
    if issue_id is None or title is None or status is None:
        return None
    return IntakeTriageRecord(
        id=issue_id,
        title=title,
        status=livespec_status_for(status=status),
        priority=_optional_int(record=record, key="priority"),
        triaged=INTAKE_TRIAGED_LABEL in _labels_of(record=record),
    )


def _labels_of(*, record: BeadsRecord) -> list[str]:
    raw = record.get("labels")
    if not isinstance(raw, list):
        return []
    items = cast("list[Any]", raw)
    return [label for label in items if isinstance(label, str)]


def _optional_str(*, record: BeadsRecord, key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) else None


def _optional_int(*, record: BeadsRecord, key: str) -> int | None:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value

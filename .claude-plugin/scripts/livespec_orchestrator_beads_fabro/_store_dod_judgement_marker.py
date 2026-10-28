"""The marker that says a Definition-of-Done judgement was recorded against an item.

The held-Definition-of-Done lane of `needs-attention` has to find, among every
backlog, ready or pending-approval item, the ones a refusing verdict is standing
against. The verdict is a ledger COMMENT and a comment read is one `bd comments`
subprocess per item, so asking every heldable item cost 282 reads in one measured
snapshot (1.4 s each) to find a verdict most of them had never had.

The marker is a label on the ITEM, so it rides the record the tenant listing
already returns: one listing names every item a judgement was ever recorded
against, and only those items need their comments read. It is written by the same
sanctioned writer that appends the comment, so the two can disagree only for a
record written before the marker existed.

A narrow RAW read, mirroring `_store_merge_hold`: the label is not a field of the
shared `WorkItem` model, which this repository does not own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DOD_JUDGEMENT_RECORDED_LABEL",
    "mark_work_item_dod_judgement_recorded",
    "read_dod_judged_work_item_ids",
]

DOD_JUDGEMENT_RECORDED_LABEL = "dod-judgement:recorded"


def mark_work_item_dod_judgement_recorded(*, path: StoreConfig, item_id: str) -> None:
    """Stamp the marker on one item; adding it to an item that carries it is a no-op."""
    make_beads_client(config=path).update_issue(
        issue_id=item_id, add_labels=[DOD_JUDGEMENT_RECORDED_LABEL]
    )


def read_dod_judged_work_item_ids(*, path: StoreConfig) -> frozenset[str]:
    """Every tenant id the marker is on, read from ONE listing of the tenant.

    Fail-SOFT per record, as the merge-hold read is: a record with no usable id,
    or whose labels are not a list, contributes nothing rather than failing the
    whole enumeration.
    """
    judged: set[str] = set()
    for record in make_beads_client(config=path).list_issues():
        issue_id = record.get("id")
        raw_labels = record.get("labels")
        if not isinstance(issue_id, str) or not isinstance(raw_labels, list):
            continue
        if DOD_JUDGEMENT_RECORDED_LABEL in cast("list[object]", raw_labels):
            judged.add(issue_id)
    return frozenset(judged)

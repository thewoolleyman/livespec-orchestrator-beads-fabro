"""Answer-disposition label vocabulary for the beads-backed work-item store.

Owns the whole `answer:` vocabulary the fifth dispatcher policy setting names
in the dispatcher-policy-settings contract in `SPECIFICATION/contracts.md`: the
per-item `answer:<human|consensus>` label written at capture or groom time, and
the narrow tenant-wide read the attention snapshot needs. It sits beside
`_store_merge_hold` for the reason that module gives — `_store_mutations` is at
its LLOC ceiling, and a one-marker vocabulary is cohesive on its own.

The label carries a VALUE rather than only itself, which is what separates it
from the merge hold: a hold's PRESENCE is the hold, while an answer disposition
names which actor class may answer. So the labels are returned RAW and
unvalidated here. Which value wins — and the asymmetry that a label may only
LOWER an item to `human` and MUST NOT raise one to `consensus` — belongs to
`effective_answer_disposition`, which also holds the global default this reader
has no business knowing about. A reader that pre-resolved the value would be a
second authority on a question the policy layer already answers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ANSWER_DISPOSITION_LABEL_PREFIX",
    "read_answer_disposition_labels",
]

ANSWER_DISPOSITION_LABEL_PREFIX = "answer:"


def read_answer_disposition_labels(*, path: StoreConfig) -> dict[str, tuple[str, ...]]:
    """Every tenant id's `answer:` labels, read straight from the raw records.

    A narrow RAW read, mirroring `read_merge_held_work_item_ids`: the
    disposition override is a label, and `store._record_to_work_item` decodes
    labels into the named fields the shared `WorkItem` model declares, so a
    marker that model does not carry is dropped on the floor before any consumer
    sees it.

    ONE read serves the whole attention pass. Two independent reads would be two
    authorities on one question, and disagreeing would advertise one disposition
    on one row and another on the next.

    Fail-SOFT in the shape the needs-attention readers use: a record with no
    usable id, or whose labels are not a list of strings, contributes nothing
    rather than failing the whole enumeration. That is safe in exactly one
    direction, and it is the safe one — an item whose override cannot be read
    falls through to the repository's committed default, which is `human`.
    """
    client = make_beads_client(config=path)
    return {
        issue_id: labels
        for record in client.list_issues()
        if isinstance(issue_id := record.get("id"), str)
        and (labels := _answer_labels(record=record))
    }


def _answer_labels(*, record: BeadsRecord) -> tuple[str, ...]:
    raw = record.get("labels")
    if not isinstance(raw, list):
        return ()
    labels = cast("list[object]", raw)
    return tuple(
        label
        for label in labels
        if isinstance(label, str) and label.startswith(ANSWER_DISPOSITION_LABEL_PREFIX)
    )

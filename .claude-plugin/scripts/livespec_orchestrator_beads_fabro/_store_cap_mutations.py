"""Per-item cap-override label mutation for the beads-backed work-item store.

Split from `_store_mutations` because the mutations file is at its LLOC
ceiling; this holds the one label-only write behind the operator cap-edit
drive verbs (`set-merge-on-review-cap` / `set-review-fix-cap` /
`set-acceptance-rework-cap`), whose per-item overrides the Dispatcher resolver
reads straight from raw beads labels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["update_work_item_cap"]


def update_work_item_cap(
    *,
    path: StoreConfig,
    item_id: str,
    label_prefix: str,
    value: str,
) -> None:
    """Replace an item's per-item cap-override label without changing its status.

    The Dispatcher resolver reads these caps straight from raw beads labels
    (`<label_prefix><value>`; see the `effective_*_cap` resolvers), so the write
    is label-only. Unlike `update_work_item_policy`, which enumerates the finite
    admission/acceptance enums to know which prior label to remove, the integer
    caps have an unbounded value space; so the prior label is discovered by
    reading the issue and every label carrying `label_prefix` is removed before
    the replacement is added. No status or assignee mutation is sent, so a cap
    edit cannot surprise-transition the item.
    """
    client = make_beads_client(config=path)
    record = client.show_issue(issue_id=item_id)
    existing = cast("list[Any]", record.get("labels", []))
    remove_labels = [
        label for label in existing if isinstance(label, str) and label.startswith(label_prefix)
    ]
    if remove_labels:
        client.update_issue(issue_id=item_id, remove_labels=remove_labels)
    client.update_issue(issue_id=item_id, add_labels=[f"{label_prefix}{value}"])

"""Label-only field mutations for the beads-backed work-item store.

Split from `_store_mutations`, which had reached its LLOC ceiling, along the
cohesion seam these writes already shared: each edits the labels
carrying a livespec field with no native beads home, and each deliberately
sends NO status or assignee mutation, so an edit cannot surprise-transition
the item. `_store_cap_mutations` is the sibling module holding the same shape
for the per-item cap overrides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "update_work_item_awaits_scope_override",
    "update_work_item_factory_safety",
    "update_work_item_policy",
    "update_work_item_workflow_scope_override",
]

_LABEL_ADMISSION = "admission:"
_LABEL_ACCEPTANCE = "acceptance:"
_LABEL_FACTORY_SAFETY = "factory-safety:"
_LABEL_WORKFLOW_SCOPE_OVERRIDE = "workflow-scope-override:"
_LABEL_AWAITS_SCOPE_OVERRIDE = "awaits-scope-override"

# The closed `factory_safety` enum, listed here so a write can REMOVE whichever
# member the item already carried. The reader (`store._factory_safety_from_labels`)
# takes the first `factory-safety:` label it finds, so leaving a stale member
# beside a fresh one would make which reason wins an artifact of label ordering.
_FACTORY_SAFETY_VALUES = (
    "needs-host-secrets",
    "mutates-host-machinery",
    "needs-privileged-host",
)


def update_work_item_policy(
    *,
    path: StoreConfig,
    item_id: str,
    admission_policy: str | None = None,
    acceptance_policy: str | None = None,
) -> None:
    """Edit policy labels on an existing item without changing its status.

    The operator policy-edit seam behind `drive --action`
    `set-admission:<id>:...` / `set-acceptance:<id>:...`. The write is
    label-only: it removes the previous label for each named policy field,
    adds the replacement label, and deliberately sends no status or assignee
    mutation so a policy edit cannot surprise-transition the item.
    """
    remove_labels: list[str] = []
    add_labels: list[str] = []
    if admission_policy is not None:
        remove_labels.extend(f"{_LABEL_ADMISSION}{value}" for value in ("auto", "manual"))
        add_labels.append(f"{_LABEL_ADMISSION}{admission_policy}")
    if acceptance_policy is not None:
        remove_labels.extend(
            f"{_LABEL_ACCEPTANCE}{value}" for value in ("ai-only", "human-only", "ai-then-human")
        )
        add_labels.append(f"{_LABEL_ACCEPTANCE}{acceptance_policy}")
    client = make_beads_client(config=path)
    if remove_labels:
        client.update_issue(issue_id=item_id, remove_labels=remove_labels)
    if add_labels:
        client.update_issue(issue_id=item_id, add_labels=add_labels)


def update_work_item_factory_safety(
    *,
    path: StoreConfig,
    item_id: str,
    value: str,
) -> None:
    """Record the item's host-only reason without changing its status.

    The store seam behind `drive --action set-factory-safety:<id>:<reason>`.
    Every canonical reason is removed before the supplied one is added, so a
    re-set REPLACES the recorded reason rather than leaving two labels whose
    reader would have to pick between them. Like its siblings here the write is
    label-only: the field is an intrinsic runnability axis orthogonal to the
    lifecycle, so recording it must not move the item.
    """
    client = make_beads_client(config=path)
    client.update_issue(
        issue_id=item_id,
        remove_labels=[f"{_LABEL_FACTORY_SAFETY}{known}" for known in _FACTORY_SAFETY_VALUES],
    )
    client.update_issue(issue_id=item_id, add_labels=[f"{_LABEL_FACTORY_SAFETY}{value}"])


def update_work_item_workflow_scope_override(
    *,
    path: StoreConfig,
    item_id: str,
    value: str,
) -> None:
    """Set the dispatcher workflow-scope override label without changing status."""
    client = make_beads_client(config=path)
    client.update_issue(
        issue_id=item_id,
        remove_labels=[
            f"{_LABEL_WORKFLOW_SCOPE_OVERRIDE}citation-only",
            _LABEL_AWAITS_SCOPE_OVERRIDE,
        ],
    )
    client.update_issue(
        issue_id=item_id,
        add_labels=[f"{_LABEL_WORKFLOW_SCOPE_OVERRIDE}{value}"],
    )


def update_work_item_awaits_scope_override(
    *,
    path: StoreConfig,
    item_id: str,
    value: bool,
) -> None:
    """Set or clear the dispatcher awaits-scope-override signal label."""
    client = make_beads_client(config=path)
    if value:
        client.update_issue(issue_id=item_id, add_labels=[_LABEL_AWAITS_SCOPE_OVERRIDE])
    else:
        client.update_issue(issue_id=item_id, remove_labels=[_LABEL_AWAITS_SCOPE_OVERRIDE])

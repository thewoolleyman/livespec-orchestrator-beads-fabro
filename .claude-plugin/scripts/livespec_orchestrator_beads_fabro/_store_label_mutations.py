"""Label-only field mutations for the beads-backed work-item store.

Split from `_store_mutations`, which had reached its LLOC ceiling, along the
cohesion seam these three writes already shared: each edits the labels
carrying a livespec field with no native beads home, and each deliberately
sends NO status or assignee mutation, so an edit cannot surprise-transition
the item. `_store_cap_mutations` is the sibling module holding the same shape
for the per-item cap overrides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, get_args

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.types import FactorySafety

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "FACTORY_SAFETY_REASONS",
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

# The closed host-only reason vocabulary, read off the `FactorySafety` alias
# rather than restated, so the label writer and the operator valve that grades a
# typed reason can never disagree with the field's own enum. A tuple, not a set:
# the refusal message enumerates the reasons, and the declaration order is the
# order contracts.md names them in.
FACTORY_SAFETY_REASONS: tuple[str, ...] = get_args(FactorySafety)


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
    reason: str,
) -> None:
    """Set the intrinsic host-only opt-out label without changing status.

    The write seam behind `drive --action set-factory-safety:<id>:<reason>`.
    Like `update_work_item_policy` it enumerates the field's finite enum to know
    which prior label to remove, so re-pressing the verb with a different reason
    REPLACES the recorded one rather than leaving the item carrying two. It
    deliberately sends no status or assignee mutation: `factory_safety` is
    orthogonal to the lifecycle, and an opt-out that moved the item would be the
    surprise-transition the whole label-only family exists to avoid.
    """
    client = make_beads_client(config=path)
    client.update_issue(
        issue_id=item_id,
        remove_labels=[f"{_LABEL_FACTORY_SAFETY}{value}" for value in FACTORY_SAFETY_REASONS],
    )
    client.update_issue(issue_id=item_id, add_labels=[f"{_LABEL_FACTORY_SAFETY}{reason}"])


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

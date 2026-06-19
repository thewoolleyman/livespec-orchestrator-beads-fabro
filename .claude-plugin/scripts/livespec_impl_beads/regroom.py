"""The `needs-regroom` state machine — the shared grooming-lifecycle primitive.

`needs-regroom` is the one new ledger state the grooming realization adds
(SPECIFICATION/contracts.md §"Skills — augmented versus new"). Beads' status
enum is fixed, so the custom state is realized as a beads LABEL
(`needs-regroom`) carried on the work-item, applied and cleared through the
`BeadsClient` seam — the same encoding the store layer uses for the other
bridge-owned flags (`origin:` / `gap-id:` / `resolution:`).

This module is the SHARED primitive the grooming front-ends consume; it owns
the three transitions of SPECIFICATION/scenarios.md "Scenario 9 — needs-regroom
state and transitions" and the normative clause in contracts.md
§"Gap-detectable behavior clauses":

    An item MUST enter `needs-regroom` on an intake Definition-of-Ready
    failure and MUST enter `needs-regroom` on a Dispatcher non-convergence
    bounce; groom approval MUST transition the `needs-regroom` item out by
    filing `ready` slices (the original item is regroomed-out, never
    silently dropped).

API (every verb keyword-only, per the family keyword-only-args rule):

- `enter(*, path, item_id)` — apply the `needs-regroom` label to an
  existing work-item. The downstream callers wire BOTH entry paths through
  this one verb: the capture front-ends call it on an intake
  Definition-of-Ready failure (consumer work-item `livespec-impl-beads-v7p2sq`)
  and the Dispatcher calls it on a non-convergence bounce (consumer
  work-item `livespec-impl-beads-n5kina`). Idempotent — entering an item
  already at `needs-regroom` is a no-op.
- `exit_regroom(*, path, item_id, ready_slice_ids)` — clear the
  `needs-regroom` label, but ONLY after verifying that replacement `ready`
  slices were actually filed for the item. If `ready_slice_ids` is empty,
  or any named id is absent from the tenant or not `ready`, the exit is
  REFUSED (`RegroomExitRefusedError`) and the label is left untouched —
  this is the mechanical guarantee that an item is regroomed-OUT, never
  silently dropped. The `groom` front-end (consumer work-item
  `livespec-impl-beads-6wksha`) files the approved slices via
  `capture-work-item` and then calls this verb with their ids.
- `is_needs_regroom(*, path, item_id)` — predicate over the item's
  current labels.

Per SPECIFICATION/constraints.md §"Inherited from livespec" (the
Result-vs-bugs split), EXPECTED failures raise the typed errors from
`errors.py` (`WorkItemNotFoundError`, `RegroomExitRefusedError`); genuine
bugs propagate as raised built-in exceptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_impl_beads._beads_client import make_beads_client
from livespec_impl_beads.errors import RegroomExitRefusedError, WorkItemNotFoundError

if TYPE_CHECKING:
    from livespec_impl_beads._beads_client import BeadsClient, BeadsRecord
    from livespec_impl_beads.types import StoreConfig

__all__: list[str] = [
    "NEEDS_REGROOM_LABEL",
    "READY_LABEL",
    "enter",
    "exit_regroom",
    "is_needs_regroom",
]

# The bridge-owned label realizing the `needs-regroom` ledger state. A bare
# label (no `key:value` prefix) because the state is a flag, not an enum
# carrying a value — its presence IS the state.
NEEDS_REGROOM_LABEL = "needs-regroom"

# The readiness tag the intake Definition-of-Ready checklist applies to an
# autonomously-dispatchable slice (SPECIFICATION/scenarios.md "Scenario 8 —
# Intake Definition-of-Ready triage"). `exit_regroom` requires the
# replacement slices to carry it before it will clear `needs-regroom`.
READY_LABEL = "ready"

# A beads status that is no longer a live, dispatchable slice — a "ready"
# replacement that is already closed cannot stand in for the regroomed item.
_CLOSED_STATUS = "closed"


def enter(*, path: StoreConfig, item_id: str) -> None:
    """Move a work-item into `needs-regroom` by applying the label.

    The single entry verb for BOTH paths the contract names — an intake
    Definition-of-Ready failure and a Dispatcher non-convergence bounce —
    so every path into the state is observable as the same label mutation.
    Idempotent: applying the label to an item already at `needs-regroom`
    leaves it at `needs-regroom`.

    Raises `WorkItemNotFoundError` if `item_id` is not present in the
    tenant (a transition against a phantom id is an expected failure the
    caller surfaces, not a silent no-op).
    """
    client = make_beads_client(config=path)
    _assert_present(client=client, item_id=item_id)
    client.update_issue(issue_id=item_id, add_labels=[NEEDS_REGROOM_LABEL])


def exit_regroom(
    *,
    path: StoreConfig,
    item_id: str,
    ready_slice_ids: list[str],
) -> None:
    """Transition a `needs-regroom` item OUT, but only against filed `ready` slices.

    The contract is escalate-don't-drop: an item leaves `needs-regroom`
    ONLY by being decomposed into `ready` replacement slices. This verb
    enforces that mechanically — it clears the label only after confirming
    that every id in `ready_slice_ids` names a present, non-closed,
    `ready`-labelled slice AND that at least one was named. Otherwise it
    REFUSES (`RegroomExitRefusedError`) and leaves the label in place, so
    an item is never silently dropped.

    Raises `WorkItemNotFoundError` if `item_id` itself is absent.
    """
    client = make_beads_client(config=path)
    _assert_present(client=client, item_id=item_id)
    if not ready_slice_ids:
        raise RegroomExitRefusedError(
            item_id=item_id,
            detail="no replacement slices were named (an item is regroomed-out, never dropped)",
        )
    not_ready = [
        slice_id for slice_id in ready_slice_ids if not _is_ready(client=client, slice_id=slice_id)
    ]
    if not_ready:
        raise RegroomExitRefusedError(
            item_id=item_id,
            detail=f"named replacement slices are not present-and-ready: {', '.join(not_ready)}",
        )
    client.update_issue(issue_id=item_id, remove_labels=[NEEDS_REGROOM_LABEL])


def is_needs_regroom(*, path: StoreConfig, item_id: str) -> bool:
    """Return True iff the work-item currently carries the `needs-regroom` label.

    Raises `WorkItemNotFoundError` if `item_id` is not present in the tenant.
    """
    client = make_beads_client(config=path)
    _assert_present(client=client, item_id=item_id)
    record = client.show_issue(issue_id=item_id)
    return NEEDS_REGROOM_LABEL in _labels_of(record=record)


def _assert_present(*, client: BeadsClient, item_id: str) -> None:
    """Raise `WorkItemNotFoundError` unless `item_id` is present in the tenant."""
    if not client.exists(issue_id=item_id):
        raise WorkItemNotFoundError(item_id=item_id)


def _is_ready(*, client: BeadsClient, slice_id: str) -> bool:
    """Return True iff `slice_id` is present, not closed, and carries `ready`."""
    if not client.exists(issue_id=slice_id):
        return False
    record = client.show_issue(issue_id=slice_id)
    if record.get("status") == _CLOSED_STATUS:
        return False
    return READY_LABEL in _labels_of(record=record)


def _labels_of(*, record: BeadsRecord) -> list[str]:
    """Extract the issue's label list (non-string entries dropped)."""
    raw = record.get("labels")
    if not isinstance(raw, list):
        return []
    items = cast("list[Any]", raw)
    return [label for label in items if isinstance(label, str)]

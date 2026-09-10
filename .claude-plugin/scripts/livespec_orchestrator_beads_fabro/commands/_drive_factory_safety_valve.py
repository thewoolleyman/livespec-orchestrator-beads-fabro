"""The `set-factory-safety` human valve — the intrinsic runnability axis, set by hand.

Its own module rather than a member of `_drive_policy_valves` because it is not
a policy edit. `admission_policy` and `acceptance_policy` are WINDOWS an
operator opens and closes around a lifecycle; `factory_safety` records something
INTRINSIC about the work — that it needs host secrets, mutates host machinery,
or needs a privileged host. That difference is exactly why this valve is ungated
on status where its policy siblings are windowed, and keeping the two apart is
what stops the next reader from adding a lane guard here by analogy.

What the verb exists for is ATTRIBUTION. The field shipped before any verb set
it, so the only opt-out route was a raw `bd label add` that recorded no actor
and no reason. Routing it through `drive` puts the reason on the item and the
press in the journal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._store_label_mutations import (
    update_work_item_factory_safety,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_success

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["set_factory_safety"]


def set_factory_safety(
    *, config: StoreConfig, item: WorkItem, aid: str, value: str
) -> dict[str, Any]:
    """Record the host-only reason that opts one item out of factory eligibility.

    Deliberately UNGATED on status, and that is a contract clause rather than an
    omission: contracts.md states the verb is valid in ANY lane, the `done` row
    included, because `factory_safety` is orthogonal to both the lifecycle and
    `admission_policy`. An item's host-only nature is a fact about the work, and
    a fact stays recordable after the work ships.

    The reason is graded by the action-id grammar against the field's own closed
    enum, so a value reaching here is already one of the three canonical ones.
    The write is label-only: status, assignee, and `admission_policy` — the
    orthogonal human-approval axis — are all left exactly as they were.
    """
    update_work_item_factory_safety(path=config, item_id=item.id, value=value)
    return valve_success(
        aid=aid,
        wid=item.id,
        stage="human-valve-set-factory-safety",
        status=item.status,
        assignee=item.assignee,
        msg=(
            f"Recorded {item.id}: factory_safety -> {value}; status unchanged. "
            f"The admission valve now host-routes it; driver-dispatch:{item.id} is the door."
        ),
    )

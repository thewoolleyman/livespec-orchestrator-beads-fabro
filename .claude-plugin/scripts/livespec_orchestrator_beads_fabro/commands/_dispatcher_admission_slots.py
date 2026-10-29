"""The pure slot and governing-setting arithmetic the admission valve plans with.

Split out of `_dispatcher_admission` by cohesion when the confirmation-turn seam
took that module to its file LLOC ceiling: the valve SEQUENCES an admission pass
(ledger writes, journal rows, the shared ACP verdict), while these three are the
side-effect-free questions it asks along the way -- how many slots are left, and
which setting governs an auto-approval. Only PUBLIC names cross the boundary.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "auto_approve_governing_settings",
    "budget_left",
    "ready_free_slots",
]


def budget_left(*, rework: ReworkPass, taken: int) -> int | None:
    """What is left of the pass's `--budget` after the rework leg took its share.

    `None` means unbounded — the `dispatch --item` override carries no budget,
    and the ready candidate list a `loop` hands in was already truncated to the
    budget upstream, so this only ever REMOVES the slots rework already spent.
    """
    if rework.budget is None:
        return None
    return max(0, rework.budget - taken)


def ready_free_slots(
    *,
    admittable: list[WorkItem],
    occupied: int,
    wip_cap: int | None,
    budget_left: int | None,
) -> int:
    slots = len(admittable) if wip_cap is None else max(0, wip_cap - occupied)
    if budget_left is None:
        return slots
    return min(slots, budget_left)


def auto_approve_governing_settings(*, item: WorkItem) -> tuple[str, ...]:
    if item.admission_policy == "auto":
        return ("admission:auto",)
    return ("auto_approve_ready",)

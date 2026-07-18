"""Factory-safety routing predicate for the Dispatcher planning layer.

The Dispatcher refuses to sandbox work-items whose first-class
``factory_safety`` field is non-null. Store adapters may still map legacy
routing markers into that field on read, but the Dispatcher itself consumes
the structured WorkItem field.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_only_refusal_detail",
    "is_host_only_item",
]


def is_host_only_item(*, item: WorkItem) -> bool:
    """Return True when a work-item is intrinsically unsafe for the factory."""
    return item.factory_safety is not None


def host_only_refusal_detail(*, item_id: str) -> str:
    """Build the actionable refusal message for a factory-unsafe item."""
    return (
        f"factory-safety refusal: work-item {item_id} carries non-null "
        "factory_safety and MUST NOT be dispatched to a fabro sandbox. "
        "Host-route it to a host sub-agent instead; the item remains open "
        "for that route."
    )

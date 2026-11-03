"""The free pre-launch screen for legacy factory-safety labels."""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.factory_safety import (
    out_of_enum_factory_safety_finding,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["out_of_enum_factory_safety_refusal"]


def out_of_enum_factory_safety_refusal(*, items: Sequence[WorkItem]) -> str | None:
    """Refuse a legacy label before any pre-launch provider or factory work."""
    for item in items:
        finding = out_of_enum_factory_safety_finding(value=item.factory_safety)
        if finding is not None:
            return f"ERROR: work-item {item.id}: {finding}"
    return None

"""The closed factory-safety label vocabulary and its legacy-label finding."""

from __future__ import annotations

from typing import get_args

from livespec_orchestrator_beads_fabro.types import FactorySafety

__all__: list[str] = [
    "FACTORY_SAFETY_REASONS",
    "out_of_enum_factory_safety_finding",
]


FACTORY_SAFETY_REASONS: tuple[str, ...] = get_args(FactorySafety)


def out_of_enum_factory_safety_finding(*, value: str | None) -> str | None:
    """Name a legacy factory-safety value outside the shared closed enum."""
    if value is None or value in FACTORY_SAFETY_REASONS:
        return None
    return (
        f"factory-safety label value {value!r} is outside the canonical enum; "
        f"expected one of {', '.join(FACTORY_SAFETY_REASONS)}."
    )

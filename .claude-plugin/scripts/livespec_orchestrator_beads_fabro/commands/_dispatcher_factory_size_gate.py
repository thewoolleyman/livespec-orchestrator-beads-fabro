"""Adopted assertion-count admission gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from returns.io import IOResult
from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count import (
    assertion_count_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "FactorySizeDecision",
    "factory_size_decision",
    "resolve_adopted_assertion_count_ceiling",
]

ADOPTED_ASSERTION_COUNT_CEILING = "adopted_assertion_count_ceiling"


@dataclass(frozen=True, kw_only=True)
class FactorySizeDecision:
    """One item's result at the conditional factory-size gate."""

    disposition: str
    adopted_ceiling: int | None
    assertion_count: int
    reason: str | None
    size_justified: bool


def factory_size_decision(
    *, item: WorkItem, adopted_ceiling: int | None, raw_justification: object
) -> FactorySizeDecision:
    """Apply the adopted ceiling to the sanctioned effective-criteria count."""
    observed = assertion_count_for(item=item).count
    del raw_justification
    if adopted_ceiling is not None:
        return FactorySizeDecision(
            disposition="decompose",
            adopted_ceiling=adopted_ceiling,
            assertion_count=observed,
            reason=(
                f"adopted assertion-count ceiling {adopted_ceiling}; "
                f"sanctioned-parser assertion count {observed}; "
                "missing or invalid size_justification; route to backlog for decomposition"
            ),
            size_justified=False,
        )
    return FactorySizeDecision(
        disposition="proceed",
        adopted_ceiling=adopted_ceiling,
        assertion_count=observed,
        reason=None,
        size_justified=False,
    )


def resolve_adopted_assertion_count_ceiling(
    *, cwd: Path
) -> IOResult[int | None, PolicySettingUnreadable]:
    """Read the committed-only ceiling, where absence means no adoption."""
    return read_dispatcher_config_value(cwd=cwd, key=ADOPTED_ASSERTION_COUNT_CEILING).bind_result(
        lambda value: _adopted_ceiling_value(value=value)
    )


def _adopted_ceiling_value(*, value: object) -> Result[int | None, PolicySettingUnreadable]:
    if value is None:
        return Success(None)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=ADOPTED_ASSERTION_COUNT_CEILING,
            detail=(
                "dispatcher.adopted_assertion_count_ceiling must be a positive integer; "
                f"got {value!r}"
            ),
        )
    )

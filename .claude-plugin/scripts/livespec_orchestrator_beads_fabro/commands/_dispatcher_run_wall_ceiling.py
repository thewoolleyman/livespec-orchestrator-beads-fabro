"""Resolution of the hard ceiling that bounds a progressing factory run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
    PER_DISPATCH_ARGUMENT_LAYER,
    RunWallBudget,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
    positive_int_seconds,
)

__all__: list[str] = [
    "DEFAULT_RUN_WALL_CEILING",
    "RUN_WALL_CEILING_ARGUMENT",
    "RUN_WALL_CEILING_KEY",
    "RunWallCeiling",
    "run_wall_ceiling_from_block",
    "run_wall_ceiling_journal_record",
]

RUN_WALL_CEILING_KEY = "dispatcher.run_wall_ceiling_seconds"
RUN_WALL_CEILING_ARGUMENT = "--run-wall-ceiling-seconds"
_CEILING_BLOCK_KEY = "run_wall_ceiling_seconds"
_DEFAULT_LAYER = WORKFLOW_DEFAULT_LAYER


@dataclass(frozen=True, kw_only=True)
class RunWallCeiling:
    """The absolute slot-holding ceiling for one dispatch and its source layer."""

    seconds: float
    layer: str


DEFAULT_RUN_WALL_CEILING = RunWallCeiling(
    seconds=DEFAULT_RUN_WALL_BUDGET.seconds * 3,
    layer=_DEFAULT_LAYER,
)


def run_wall_ceiling_from_block(
    *, block: dict[str, Any], budget: RunWallBudget, argument: str | None = None
) -> RunWallCeiling | str:
    """Resolve and validate the ceiling after the budget it must not undercut."""
    configured = _configured_ceiling(block=block, budget=budget)
    if isinstance(configured, str) or argument is None:
        return configured
    parsed = _argument_ceiling(argument=argument)
    if isinstance(parsed, str):
        return parsed
    return _validate(ceiling=parsed, budget=budget)


def run_wall_ceiling_journal_record(*, ceiling: RunWallCeiling) -> dict[str, object]:
    """Project the frozen ceiling and its source alongside the dispatch budget."""
    return {"run_wall_ceiling": {"seconds": ceiling.seconds, "layer": ceiling.layer}}


def _configured_ceiling(*, block: dict[str, Any], budget: RunWallBudget) -> RunWallCeiling | str:
    raw = block.get(_CEILING_BLOCK_KEY)
    if raw is None:
        return RunWallCeiling(seconds=budget.seconds * 3, layer=_DEFAULT_LAYER)
    seconds = positive_int_seconds(value=raw)
    if seconds is None:
        return f"{RUN_WALL_CEILING_KEY} must be a positive integer of seconds; got {raw!r}"
    return _validate(
        ceiling=RunWallCeiling(seconds=float(seconds), layer=REPOSITORY_LAYER), budget=budget
    )


def _argument_ceiling(*, argument: str) -> RunWallCeiling | str:
    seconds = positive_int_seconds(value=int(argument) if argument.isdigit() else None)
    if seconds is None:
        return (
            f"{RUN_WALL_CEILING_ARGUMENT} must be a positive integer of seconds; "
            f"got {argument!r}"
        )
    return RunWallCeiling(seconds=float(seconds), layer=PER_DISPATCH_ARGUMENT_LAYER)


def _validate(*, ceiling: RunWallCeiling, budget: RunWallBudget) -> RunWallCeiling | str:
    if ceiling.seconds < budget.seconds:
        return (
            f"{RUN_WALL_CEILING_KEY} is {int(ceiling.seconds)} seconds (layer: {ceiling.layer}), "
            f"smaller than {int(budget.seconds)} seconds from dispatcher.run_wall_budget_seconds "
            f"(layer: {budget.layer})"
        )
    return ceiling

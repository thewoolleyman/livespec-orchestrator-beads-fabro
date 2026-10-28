"""Read the result a causal supersession proposes to make the plan owe."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    read_plan_owned_result,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["supersession_replacement_observation"]


def supersession_replacement_observation(
    *,
    config: StoreConfig,
    epic_id: str,
    required_result: object | None,
    supersession: object | None,
    now: str,
) -> ResultObservation | None:
    """Read the candidate through the same plan-owned redirect as the prior result."""
    if supersession is None or required_result is None:
        return None
    return read_plan_owned_result(
        config=config,
        epic_id=epic_id,
        required_result=required_result,
        now=now,
    )

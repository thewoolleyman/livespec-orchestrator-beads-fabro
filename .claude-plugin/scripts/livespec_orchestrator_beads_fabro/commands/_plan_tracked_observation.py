"""Observe a tracked plan's prior obligation before deciding its successor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_obligation import obligation_of
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import (
    read_plan_owned_result,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["prior_observation"]


def prior_observation(
    *, config: StoreConfig, epic_id: str, authority: AuthorityState, now: str
) -> ResultObservation | None:
    """Read the authority-held target through the plan-owned redirect."""
    obligation = obligation_of(authority=authority)
    if obligation is None:
        return None
    return read_plan_owned_result(
        config=config,
        epic_id=epic_id,
        required_result=obligation.required_result,
        now=now,
    )

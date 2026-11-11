"""Resolve the credential-use window from the dispatch's wall-clock bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance import (
    credential_queue_allowance_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_window import (
    credential_use_window_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    run_wall_budget_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_ceiling import (
    run_wall_ceiling_from_block,
)

__all__: list[str] = [
    "CredentialUseWindow",
    "credential_use_window_from_block",
]


@dataclass(frozen=True, kw_only=True)
class CredentialUseWindow:
    """The window and its queue half, resolved from one config block."""

    window_seconds: int
    queue_allowance_seconds: int


def credential_use_window_from_block(*, block: dict[str, Any]) -> CredentialUseWindow | str:
    """Resolve the queue plus hard-ceiling window, or return its configuration error."""
    queue_allowance = credential_queue_allowance_from_block(block=block)
    if isinstance(queue_allowance, str):
        return queue_allowance
    wall_budget = run_wall_budget_from_block(block=block)
    if isinstance(wall_budget, str):
        return wall_budget
    wall_ceiling = run_wall_ceiling_from_block(block=block, budget=wall_budget)
    if isinstance(wall_ceiling, str):
        return wall_ceiling
    return CredentialUseWindow(
        window_seconds=credential_use_window_seconds(
            queue_allowance_seconds=queue_allowance.seconds,
            run_wall_budget_seconds=int(wall_ceiling.seconds),
        ),
        queue_allowance_seconds=queue_allowance.seconds,
    )

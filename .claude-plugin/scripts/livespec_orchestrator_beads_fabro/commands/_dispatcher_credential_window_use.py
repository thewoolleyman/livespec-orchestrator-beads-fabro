"""The bounded credential-use window a dispatch's credential requirement adds to its allowance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance import (
    credential_queue_allowance_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement_types import (
    WorkflowFaultDeferral,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_window import (
    credential_use_window_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    run_wall_budget_from_block,
)

__all__: list[str] = ["CredentialUseWindow", "credential_use_window"]


@dataclass(frozen=True, kw_only=True)
class CredentialUseWindow:
    """The window and the queue half of it, resolved from one read of the block.

    Both halves travel together because the status surfaces report queue time
    consumed against the queue allowance while the gate enforces the window, and
    a reader cannot recover an addend from a sum.
    """

    window_seconds: int
    queue_allowance_seconds: int


def credential_use_window(*, block: dict[str, Any]) -> CredentialUseWindow | WorkflowFaultDeferral:
    """The bounded credential-use window for this dispatch, or the owning fault.

    BOTH keys are resolved from the SAME block read the node timeouts came from,
    for the reason `prepare_workflow_payload` reads them together: the two
    figures are summed into one bound, and two reads of the same configuration
    could produce a window neither key's refusal would describe.

    A malformed value is a `WorkflowFaultDeferral` rather than a credential
    refusal, which is the same routing `node_timeouts_from_block`'s refusal
    takes one function up and for the same reason: the dispatch-admission stage
    OWNS both keys, refuses them with its own diagnostic before any run exists,
    and a credential wall answering first leaves that stage silent.
    """
    queue_allowance = credential_queue_allowance_from_block(block=block)
    if isinstance(queue_allowance, str):
        return WorkflowFaultDeferral(
            message=f"credential lifetime requirement unresolved: {queue_allowance}"
        )
    wall_budget = run_wall_budget_from_block(block=block)
    if isinstance(wall_budget, str):
        return WorkflowFaultDeferral(
            message=f"credential lifetime requirement unresolved: {wall_budget}"
        )
    return CredentialUseWindow(
        window_seconds=credential_use_window_seconds(
            queue_allowance_seconds=queue_allowance.seconds,
            run_wall_budget_seconds=int(wall_budget.seconds),
        ),
        queue_allowance_seconds=queue_allowance.seconds,
    )

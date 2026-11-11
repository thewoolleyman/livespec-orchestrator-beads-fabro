"""The outcome retained when a dropped client leaves its server run unreadable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    DEAD_IMPLEMENTER_SENTINEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
    RECAPTURE_EXHAUSTED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
        DispatchOutcome,
    )

__all__: list[str] = ["unobservable_run_outcome"]

_TERMINAL_STATUS_KINDS = frozenset(
    {"succeeded", "failed", "cancelled", "canceled", "blocked", "human_input_required"}
)
_CLIENT_TERMINAL_SENTINELS = (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
    RECAPTURE_EXHAUSTED_MARKER,
    DEAD_IMPLEMENTER_SENTINEL,
)


def unobservable_run_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    client_text: str,
) -> DispatchOutcome | None:
    """Retain ownership when a failed client leaves its bound run unobservable.

    A terminal client sentinel outranks an unanswered inspection because it is
    positive evidence that the server run reached a terminal node. Otherwise,
    a run that cannot be observed remains claimed rather than being relaunched.
    """
    if (
        run_id is None
        or inspect is None
        or (inspect.command.exit_code == 0 and inspect.status_kind in _TERMINAL_STATUS_KINDS)
        or any(sentinel in client_text for sentinel in _CLIENT_TERMINAL_SENTINELS)
    ):
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="run-unobservable",
        stage="fabro-reattach",
        pr_number=None,
        merge_sha=None,
        fabro_run_id=run_id,
        detail=(
            f"run {run_id} on {plan.fabro_factory_server or 'the local factory'} "
            "is possibly still alive; re-attach observation budget exhausted; "
            "work-item claim retained"
        ),
    )

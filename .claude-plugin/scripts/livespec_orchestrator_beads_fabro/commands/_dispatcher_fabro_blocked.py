"""Render and classify Fabro runs that stopped at the human terminal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import (
    FabroEscalation,
    fabro_escalation_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

__all__: list[str] = ["blocked_outcome"]

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )


def blocked_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
) -> DispatchOutcome | None:
    """Return the terminal outcome when Fabro deliberately parked for a human.

    A foreground ``fabro run`` exits non-zero when it returns at a human gate,
    so the exit code alone cannot distinguish blocked from failed.  The engine
    parses the run id from the CLI output and reads the authoritative status via
    ``fabro inspect --json``.  Anything other than a confirmed blocked status
    falls back to exit-code routing.
    """
    if run_id is None or inspect is None:
        return None
    if inspect.command.exit_code != 0:
        return None
    if inspect.status_kind not in {"blocked", "human_input_required"}:
        return None
    failure = inspect.failure
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=_blocked_detail(
            run_id=run_id,
            server_url=plan.fabro_factory_server,
            escalation=fabro_escalation_from_payload(payload=inspect.payload),
        ),
        fabro_run_id=run_id,
        fabro_failure_cause=None if failure is None else failure.cause,
        fabro_failure_category=None if failure is None else failure.category,
        fabro_failure_signature=None if failure is None else failure.signature,
        provider_usage_limit=False if failure is None else failure.provider_usage_limit,
        provider_usage_limit_provider=(
            None if failure is None else failure.provider_usage_limit_provider
        ),
    )


def _blocked_detail(
    *,
    run_id: str,
    server_url: str | None,
    escalation: FabroEscalation | None,
) -> str:
    """Render the blocked terminal for the operator who has to triage it.

    Every ``fabro`` command named here carries its factory.  A bare attach
    defaults to the local server and can plausibly report a remote run missing.
    Engine-escalated and genuinely gated runs share a terminal status but need
    different next steps, so the former names its recorded failure rather than
    offering a question that no agent asked.
    """
    factory = "" if server_url is None else f" --server {server_url}"
    if escalation is None:
        return (
            f"run {run_id} parked at the in-loop human gate (needs-human); "
            f"answer with `fabro attach {run_id}{factory}` while the engine lives, "
            f"`fabro resume {run_id}{factory}` only if the engine died; "
            "not auto-resumed, item left open"
        )
    signatures = ", ".join(escalation.loop_failure_signatures)
    return (
        f"run {run_id} was ESCALATED by the engine to the "
        f"`{escalation.next_node_id}` node after a non-retryable failure; "
        "no agent asked anything, so there is no gate question and no answer "
        "to give — attaching to the run cannot clear it; "
        f"recorded loop failure signature: {signatures}; "
        "triage that failure, not the run; not auto-resumed, item left open"
    )

"""Fabro run terminal-state helpers for the dispatcher engine."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    dead_implementer_condition_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    tail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_blocked import (
    blocked_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import (
    inspect_run,
    unobservable_run_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_terminal import (
    needs_human_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    RECAPTURE_EXHAUSTED_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    provider_limit_release_outcome,
    reclassified_turns,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recapture_exhausted import (
    recapture_exhausted_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_acquire_failure import (
    sandbox_acquire_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    terminal_event_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )

NON_CONVERGED_NODE = "non_converged"

__all__: list[str] = [
    "fabro_run_terminal_outcome",
    "inspect_run",
    "janitor_succeeded",
]


def fabro_run_terminal_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    exit_code: int,
    stderr: str,
) -> DispatchOutcome | None:
    """Return a non-green run observation, or None for ordinary PR reconciliation.

    EVERY non-green ending carries the run's reclassified turns, whichever
    mapping below produced it: a refusal booked as a successful turn mints its
    candidate hold even when a later failure kept its own route, so the evidence
    rides the outcome the disposition reads instead of being re-derived there.
    """
    outcome = _terminal_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        exit_code=exit_code,
        stderr=stderr,
    )
    if outcome is None:
        return None
    turns = reclassified_turns(plan=plan, inspect=inspect, run_id=run_id)
    return replace(outcome, reclassified_turns=turns) if turns else outcome


def _terminal_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    exit_code: int,
    stderr: str,
) -> DispatchOutcome | None:
    """The terminal mapping itself, before the reclassified turns are attached."""
    # FIRST, because the clause releases a provider-limit failure "through any
    # terminal, the workflow's `needs_human` terminal included" -- so it has to
    # outrank BOTH mappings below that would otherwise rest the item at
    # `blocked`. It costs a green run nothing: a succeeded run records no
    # failure, and the reading returns before touching configuration.
    released = provider_limit_release_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        stderr=stderr,
    )
    if released is not None:
        return released
    blocked = blocked_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
    )
    if blocked is not None:
        return blocked
    cancelled = _engine_cancelled(inspect=inspect)
    if not cancelled and (
        exit_code == 0
        or (
            inspect is not None
            and inspect.command.exit_code == 0
            and inspect.status_kind == "succeeded"
        )
    ):
        return None
    failure = None if inspect is None else inspect.failure
    detail = fabro_failure_outcome_detail(failure=failure, fallback=tail(text=stderr))
    # BOTH channels the sentinel-driven mappings below read, assembled before
    # the unobservable branch so that branch can stand aside for a terminal
    # verdict the client already proved. Deciding unobservability first made it
    # shadow every such verdict, which is the whole hazard its own docstring
    # records.
    client_text = f"{stderr}\n{detail}"
    unobservable = unobservable_run_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        client_text=client_text,
    )
    if unobservable is not None:
        return unobservable
    terminated = sandbox_acquire_failure_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        failure=failure,
    )
    if terminated is None:
        terminated = needs_human_terminal_outcome(
            outcome_type=outcome_type,
            plan=plan,
            run_id=run_id,
            inspect=inspect,
            failure=failure,
            text=client_text,
        )
    # AFTER the needs-human terminal and BEFORE the generic failure, because the
    # `non_converged` terminal also ends a recapture-cap run and the generic arm
    # would hand its detail to the non-convergence bounce.
    if terminated is None:
        terminated = recapture_exhausted_outcome(
            outcome_type=outcome_type,
            plan=plan,
            run_id=run_id,
            failure=failure,
            emitted=terminal_event_output(
                payload=None if inspect is None else inspect.events_payload,
                node=NON_CONVERGED_NODE,
                marker=RECAPTURE_EXHAUSTED_MARKER,
            ),
            client_text=client_text,
        )
    if terminated is not None:
        return terminated
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="cancelled" if cancelled else "failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=detail,
        fabro_run_id=run_id,
        fabro_factory_name=plan.fabro_factory_name if cancelled else None,
        janitor_green=janitor_succeeded(inspect=inspect) if cancelled else None,
        fabro_failure_cause=None if failure is None else failure.cause,
        fabro_failure_category=None if failure is None else failure.category,
        fabro_failure_signature=None if failure is None else failure.signature,
        provider_usage_limit=False if failure is None else failure.provider_usage_limit,
        provider_usage_limit_provider=(
            None if failure is None else failure.provider_usage_limit_provider
        ),
        # The breaker's sentinel can arrive on EITHER channel and neither is
        # guaranteed: the raw `fabro run` stderr is tail-truncated, and the
        # structured cause chain need not carry a node's own output at all. Both
        # are read, because a probe aimed at one channel would report a clean
        # "no truncation" for a truncation carried on the other.
        dead_implementer_condition=dead_implementer_condition_from_text(text=f"{stderr}\n{detail}"),
    )


def _engine_cancelled(*, inspect: FabroInspectResult | None) -> bool:
    """Whether the engine, rather than the Dispatcher watchdog, cancelled the run."""
    if inspect is None:
        return False
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None:
        return False
    status: object = record.get("status")
    if not isinstance(status, dict):
        return False
    reason: object = cast("dict[str, object]", status).get("reason")
    return reason == "cancelled"


def janitor_succeeded(*, inspect: FabroInspectResult | None) -> bool:
    """Whether the run record proves that a janitor visit succeeded."""
    if inspect is None:
        return False
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None:
        return False
    stages = record.get("stages")
    if not isinstance(stages, dict):
        return False
    for name, value in cast("dict[str, object]", stages).items():
        if name.split("@", maxsplit=1)[0] != "janitor":
            continue
        if isinstance(value, dict) and cast("dict[str, object]", value).get("state") == "succeeded":
            return True
    return False

"""Fabro run terminal-state helpers for the dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked_gate_outcome import (
    blocked_gate_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    dead_implementer_condition_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    tail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_reattach import (
    inspect_run,
    unobservable_run_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_verdict import (
    hook_verdict_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
    needs_human_terminal_preservation,
    needs_human_terminal_reason,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    provider_limit_release_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recapture_exhausted import (
    recapture_exhausted_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    routing_stage_failure,
    terminal_event_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import causal_stage_failure
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )

__all__: list[str] = [
    "fabro_run_terminal_outcome",
    "inspect_run",
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
    """Return a non-green run observation, or None for ordinary PR reconciliation."""
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
    blocked = blocked_gate_outcome(
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
    terminated = _needs_human_terminal_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
        failure=failure,
        text=client_text,
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


def _needs_human_terminal_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    failure: FabroFailureDetail | None,
    text: str,
) -> DispatchOutcome | None:
    """Map the `needs_human` terminal's sentinel onto the `blocked` outcome.

    A run whose `non_converged` terminal named the RECAPTURE cap instead prints no
    needs-human sentinel; it is mapped by `recapture_exhausted_outcome` onto the
    same `blocked` rest, so a proof record that kept failing review is repaired
    rather than bounced to `backlog` as a janitor non-convergence.

    The workflow's needs-human path no longer parks the run (plan
    ledger-is-the-only-gate; contracts.md "A factory run never awaits a
    human", v093): the terminal node preserves the tree on a run-scoped ref,
    prints `NEEDS_HUMAN_MARKER` and exits non-green. What the Dispatcher owes
    the ledger is unchanged — the item rests at `blocked / needs-human` and
    the dispatch reports exit code 4 — so the sentinel produces the very same
    `blocked` outcome the gate did, with a detail that names the preserved
    ref and the ledger valve instead of a `fabro attach` that would find no
    run to attach to. The terminal's stage event supplies its emitted output;
    client stderr and structured detail remain fallbacks for legacy records.
    Neither fallback is guaranteed to carry a node's own output.

    EVERY STRUCTURED FAILURE FIELD IS CARRIED, exactly as the sibling `failed`
    outcome below carries them. Passing none of them is what made the
    engine-escalation rendering of `bd-ib-bg2zz5` unreachable for every v093
    terminal ending, which since v093 is every needs-human ending: the one line
    a triager needs — the causal stage, its category and its innermost cause —
    survived only in the run export. The ledger STATUS is deliberately
    unchanged (`bg2zz5`'s own ruling: a presentation defect over accurate state
    is fixed in the presentation), so the item still rests at `blocked /
    needs-human` and only what the outcome REPORTS grows.

    THE TWO PROVIDER FIELDS ARE LOAD-BEARING RATHER THAN DECORATIVE, which is
    why they are listed beside the three taxonomy fields and not left for a
    consumer to recover from `detail` prose. `record_provider_exhaustion_if_
    observed` keys on `provider_usage_limit_provider` alone, so dropping it here
    meant a ceiling observed at a needs-human ending wrote NO dispatcher-owned
    hold — and the next dispatch burned the same exhausted credential.

    THE TERMINAL'S OWN REASON IS PARSED ONCE AND CARRIED, for the same reason
    and from the same text the detail is rendered from. The durable ledger
    record is appended long after this mapper, from the outcome alone, so a
    reason left only inside `detail` would reach it only as prose to re-match —
    and for a stage that TIMED OUT that line is the sole account of what the
    half-finished turn left behind (work-item bd-ib-qhv7qs).

    THE CAUSAL VERDICT IS COMPUTED ONCE AND CARRIED, rather than rendered into
    the detail and recovered downstream. The escalation that writes this
    ending's operator guidance to stderr needs the same three-way verdict the
    detail is rendered from, and it runs long after this mapper with no access
    to the inspect payload — so a second derivation there could only read the
    rendered prose back, which is the coupling every typed field above exists
    to avoid. One verdict, two surfaces, no reparse.

    AND ON AN ENGINE-ROUTED ENDING THE CAUSE IS RE-READ FROM THE STAGE THAT
    ROUTED IT. The observed failure comes from the run CONCLUSION, which on
    exactly these endings describes the terminal's own deliberate exit — so
    `_head` above names the routing stage while `_attribution` quoted a
    sentence about the graph's shape beside it, and the two read as one
    account. The re-read is gated on the causal verdict having named a stage,
    because that verdict is the only thing that establishes an engine-routed
    ending; an agent-request ending has no predecessor to ask, and an
    unestablished one has nothing to ask it with. What the re-read may not
    retract is the provider ceiling, which `_dispatcher_terminal_events`
    records in full.
    """
    emitted = terminal_event_output(payload=None if inspect is None else inspect.events_payload)
    text = f"{emitted}\n{text}"
    if NEEDS_HUMAN_MARKER not in text:
        return recapture_exhausted_outcome(
            outcome_type=outcome_type, plan=plan, run_id=run_id, text=text
        )
    causal = causal_stage_failure(
        evidence=None if inspect is None else terminal_evidence(payload=inspect.payload)
    )
    if inspect is not None and causal.stages:
        failure = routing_stage_failure(
            observed=failure,
            inspect_payload=inspect.payload,
            events_payload=inspect.events_payload,
            stage=causal.stages[-1],
        )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=needs_human_terminal_detail(
            work_item_id=plan.work_item_id,
            run_id=run_id,
            text=text,
            causal=causal,
            failure=failure,
        ),
        needs_human_kind=causal.kind,
        needs_human_stages=causal.stages,
        needs_human_reason=needs_human_terminal_reason(text=text),
        needs_human_preservation=needs_human_terminal_preservation(text=text),
        # The routing stage's RECORDED commit verdict (bd-ib-k3nmbi): on 8zyan the
        # stage's failure_reason was the agent's own "the Green amend hook did not
        # complete" while the record held the hook's completed refusal.
        hook_verdict=hook_verdict_for(inspect=inspect, stages=causal.stages),
        fabro_run_id=run_id,
        fabro_failure_cause=None if failure is None else failure.cause,
        fabro_failure_category=None if failure is None else failure.category,
        fabro_failure_signature=None if failure is None else failure.signature,
        provider_usage_limit=False if failure is None else failure.provider_usage_limit,
        provider_usage_limit_provider=(
            None if failure is None else failure.provider_usage_limit_provider
        ),
    )

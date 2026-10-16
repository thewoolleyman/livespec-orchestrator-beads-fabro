"""Fabro run terminal-state helpers for the dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
    needs_human_terminal_preservation,
    needs_human_terminal_reason,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    terminal_event_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import causal_stage_failure
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import (
    FabroEscalation,
    fabro_escalation_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
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
    blocked = _blocked_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
    )
    if blocked is not None:
        return blocked
    if exit_code == 0 or (
        inspect is not None
        and inspect.command.exit_code == 0
        and inspect.status_kind == "succeeded"
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
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=detail,
        fabro_run_id=run_id,
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
    """
    emitted = terminal_event_output(payload=None if inspect is None else inspect.events_payload)
    text = f"{emitted}\n{text}"
    if NEEDS_HUMAN_MARKER not in text:
        return None
    causal = causal_stage_failure(
        evidence=None if inspect is None else terminal_evidence(payload=inspect.payload)
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

    Every `fabro` command named here carries the FACTORY it must be aimed at.
    That suffix is part of the command, not decoration: a bare `fabro attach
    <run>` defaults to the LOCAL server, and against a run living on a remote
    factory it reports "No running processes found" — a clean, plausible, wrong
    answer with no error, which sends the triager hunting for a run that was
    never missing. The suffix is omitted only when the resolved factory HAS no
    server url, i.e. the single-factory local default, where naming one would be
    inventing a target rather than recording the resolved one.

    An ENGINE-ESCALATED run and a run genuinely parked on a human gate share
    one terminal status, so a single wording has to be wrong for one of them.
    It used to be wrong for the escalated run: it announced a gate, which sent
    the triager hunting for a question no agent had asked, and invited an
    attach that could not help because the failure is deterministic and its
    retry budget was already spent. Measured cost of that hunt on one incident:
    roughly twenty hours instead of twenty minutes.

    So the escalated run gets its own message, naming the escalation node and
    the loop failure signature the engine recorded — the thing actually worth
    triaging — and pointedly NOT offering a gate to answer. The genuine gate
    keeps the original wording verbatim.
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


def _blocked_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
) -> DispatchOutcome | None:
    """Detect a run parked at the in-loop human gate (third terminal state).

    A foreground `fabro run` exits non-zero when it returns at a human
    gate, so the exit code alone cannot distinguish blocked from failed:
    the engine parses the run id from the CLI output and reads the
    authoritative status via `fabro inspect --json`. Anything other
    than a confirmed blocked status falls back to exit-code routing.

    The blocked STATUS is accurate for an engine-escalated run too, and is
    deliberately left alone; only the operator-facing rendering splits, via
    `_blocked_detail`.
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

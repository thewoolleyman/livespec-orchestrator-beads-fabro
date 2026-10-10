"""Fabro run terminal-state helpers for the dispatcher engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    dead_implementer_condition_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    journal_stage,
    tail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import (
    FabroEscalation,
    fabro_escalation_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroInspectResult,
    fabro_port_for_plan,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )

__all__: list[str] = [
    "fabro_run_terminal_outcome",
    "inspect_run",
]

_FABRO_INSPECT_TIMEOUT_SECONDS = 300.0
_PRESERVED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PRESERVED: "


def inspect_run(
    *,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    run_id: str | None,
) -> FabroInspectResult | None:
    """Read and journal `fabro inspect --json` for a parsed run id."""
    if run_id is None:
        return None
    inspect = fabro_port_for_plan(plan=plan, runner=runner).inspect(
        run_id=run_id,
        timeout_seconds=_FABRO_INSPECT_TIMEOUT_SECONDS,
    )
    journal_stage(
        journal=journal,
        plan=plan,
        stage="fabro-inspect",
        result=cast("CommandResult", inspect.command),
    )
    return inspect


def fabro_run_terminal_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    inspect: FabroInspectResult | None,
    exit_code: int,
    stderr: str,
) -> DispatchOutcome | None:
    """Return blocked/failed Fabro-run outcome, or None for green routing."""
    blocked = _blocked_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        inspect=inspect,
    )
    if blocked is not None:
        return blocked
    if exit_code == 0:
        return None
    failure = None if inspect is None else inspect.failure
    detail = fabro_failure_outcome_detail(failure=failure, fallback=tail(text=stderr))
    terminated = _needs_human_terminal_outcome(
        outcome_type=outcome_type,
        plan=plan,
        run_id=run_id,
        text=f"{stderr}\n{detail}",
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
    text: str,
) -> DispatchOutcome | None:
    """Map the `needs_human` terminal's sentinel onto the `blocked` outcome.

    The workflow's needs-human path no longer parks the run (plan
    ledger-is-the-only-gate; contracts.md "A factory run never awaits a
    human", v093): the terminal node preserves the tree on a run-scoped ref,
    prints `NEEDS_HUMAN_MARKER` and exits non-green. What the Dispatcher owes
    the ledger is unchanged — the item rests at `blocked / needs-human` and
    the dispatch reports exit code 4 — so the sentinel produces the very same
    `blocked` outcome the gate did, with a detail that names the ledger valve
    instead of a `fabro attach` that would find no run to attach to. It names a
    preservation ref only when the node reported a successful push; otherwise
    it names the dump pointer as the only preservation. The sentinel is read
    from BOTH the raw stderr and the structured detail, for the same reason the
    dead-implementer breaker does: neither channel is guaranteed to carry a
    node's own output.
    """
    if NEEDS_HUMAN_MARKER not in text:
        return None
    run_label = "unknown-run" if run_id is None else run_id
    marker_lines = (
        line.split(_PRESERVED_SENTINEL, 1)
        for line in text.splitlines()
        if _PRESERVED_SENTINEL in line
    )
    preserved_ref = next((parts[1].strip() for parts in marker_lines), None) or None
    preservation = (
        (
            "no run-scoped preservation ref was reported; the preserve-by-reference "
            "dump pointer is the only preservation"
        )
        if preserved_ref is None
        else (
            f"the tree was preserved on {preserved_ref} "
            "(see the preserve-by-reference pointer on the item for the dump digest)"
        )
    )
    rework_source = (
        "from the dump pointer or from scratch"
        if preserved_ref is None
        else "from the preserved ref or from scratch"
    )
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=(
            f"run {run_label} terminated at the needs_human node (needs-human); "
            f"{preservation}; no run is waiting — the decision lives in the "
            "ledger: answer with "
            f"`resolve-blocked:{plan.work_item_id}:ready` (re-dispatch, seeding rework "
            f"{rework_source}) or leave the item blocked"
        ),
        fabro_run_id=run_id,
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

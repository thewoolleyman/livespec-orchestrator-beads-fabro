"""The in-loop human-gate `blocked` terminal state of a Fabro run, mapped to an outcome.

Split out of `_dispatcher_fabro_terminal` by cohesion: this concern owns the
`blocked` / `human_input_required` status reading and the operator-facing
rendering of an engine-escalated run versus a genuine gate, and nothing else in
that module shares a private helper with it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import (
    FabroEscalation,
    fabro_escalation_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
    )

__all__: list[str] = [
    "blocked_gate_outcome",
]


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


def blocked_gate_outcome(
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

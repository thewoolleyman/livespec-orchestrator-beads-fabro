"""The operator-facing detail a needs-human terminal reports.

Split out of `_dispatcher_fabro_terminal` by cohesion: that module ROUTES a
Fabro run's exit onto one of the three terminal outcomes, while this one is the
pure rendering of the needs-human terminal's own account. Keeping the render
here is what lets it read the causal stage and the structured failure without
the routing module growing a second concern.

THE TWO ENDINGS SHARE ONE STATUS AND MUST NOT SHARE ONE WORDING, which is the
same defect `_blocked_detail` already fixed for the `blocked` status and which
the v093 terminal made unreachable again
(`plan/pr-stage-backgrounded-push-fault/research/001-failure-analysis-and-mechanism-candidates-2026-10-08.md`
section 3.5). An AGENT that ended through the needs-human protocol asked a
question and a human has something to decide; an ENGINE that routed a
non-retryable node failure here asked nothing, and telling its triager that a
decision awaits them sends them hunting for a question nobody wrote. The
discriminator is the causal stage: an agent-reported ending rides a conditional
edge off a node that SUCCEEDED, so it records no loop failure signature.

The agent-reported wording is kept BYTE-IDENTICAL to what it was before the
stage attribution existed. That ending was never mis-rendered, so changing its
text would be churn in the one arm this change is not about.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NEEDS_HUMAN_MARKER
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import CausalStageFailure
from livespec_orchestrator_beads_fabro.commands._fabro_escalation import ESCALATION_NODE_ID
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    transport_fault_clause,
    transport_fault_from_cause,
)

__all__: list[str] = [
    "needs_human_terminal_detail",
]

_UNKNOWN_RUN = "unknown-run"
_PRESERVED_POINTER = "see the preserve-by-reference pointer on the item for the dump digest"
_FALL_BACK_TO_POINTER = (
    "so rely on the preserve-by-reference pointer on the item for the dump digest"
)

# The two NEGATIVE sentinels the terminal node writes when it preserved
# nothing, derived from the ONE shared marker so a workflow edit cannot
# desynchronise them. Both CONTAIN the bare marker, so each match keys on its
# own distinguishing suffix.
_PUSH_FAILED_SENTINEL = f"{NEEDS_HUMAN_MARKER}_PUSH_FAILED"
_NO_RUN_ID_SENTINEL = f"{NEEDS_HUMAN_MARKER}_NO_RUN_ID"


def needs_human_terminal_detail(
    *,
    work_item_id: str,
    run_id: str | None,
    text: str,
    causal: CausalStageFailure | None,
    failure: FabroFailureDetail | None,
) -> str:
    """Render one needs-human terminal for the operator who has to triage it.

    `text` is the run's own output — the same channel the sentinel was matched
    on — and it is read for ONE question: whether the terminal preserved
    anything. Nothing else in the render depends on it.
    """
    run_label = _UNKNOWN_RUN if run_id is None else run_id
    clauses = (
        _head(run_label=run_label, causal=causal),
        *_attribution(causal=causal, failure=failure),
        _preservation(run_id=run_id, text=text),
        _decision(work_item_id=work_item_id),
    )
    return "; ".join(clauses)


def _head(*, run_label: str, causal: CausalStageFailure | None) -> str:
    """The opening clause, which is where the two endings part company."""
    if causal is None:
        return f"run {run_label} terminated at the {ESCALATION_NODE_ID} node (needs-human)"
    return (
        f"run {run_label} failed at {_stage_phrase(stages=causal.stages)} after a "
        f"non-retryable fault and the graph routed it to the {ESCALATION_NODE_ID} "
        "terminal — no agent asked anything, so there is no question to answer"
    )


def _stage_phrase(*, stages: tuple[str, ...]) -> str:
    """`stage pr` for one, `stages pr, review` for several — never a bare list."""
    if len(stages) == 1:
        return f"stage {stages[0]}"
    return f"stages {', '.join(stages)}"


def _attribution(
    *,
    causal: CausalStageFailure | None,
    failure: FabroFailureDetail | None,
) -> tuple[str, ...]:
    """What the engine recorded about the failure, innermost cause first.

    Empty for an agent-reported ending, which has no engine-recorded failure to
    attribute. The cause is the INNERMOST element of the chain, already selected
    by `_fabro_port_records`: the outer element is the fixed `ACP protocol
    error` wrapper, which identifies the transport and names no fault.

    The CLASSIFICATION rides beside the cause rather than replacing it. Quoting
    the cause alone already happens to contain the backgrounded command, inside
    the engine's own prose — so a reader could find the command and still have
    no idea it was a transport fault, which is the whole misreading this clause
    exists to prevent.
    """
    if causal is None:
        return ()
    clauses: list[str] = []
    if failure is not None and failure.cause is not None:
        clauses.append(f"innermost cause: {failure.cause}")
        fault = transport_fault_from_cause(cause=failure.cause)
        if fault is not None:
            clauses.append(transport_fault_clause(fault=fault))
    clauses.append(f"recorded loop failure signature: {', '.join(causal.signatures)}")
    return tuple(clauses)


def _preservation(*, run_id: str | None, text: str) -> str:
    """What a rework can start FROM — the fact the ledger answer turns on.

    The ref used to be DERIVED from the run id and asserted unconditionally, so
    a preservation push that failed read exactly like one that landed and sent
    the operator to a ref `git fetch` cannot find. The terminal node says which
    happened; this reads it.

    SILENCE IS THE PRESERVED ARM, deliberately. Only an explicit negative
    sentinel — or an unparsed run id, which makes a run-scoped ref unnameable
    on its face — retracts the ref. A record that reports neither outcome is
    the ordinary one, and treating it as failure would retract a ref that is
    really there, which is the mirror-image lie.
    """
    if run_id is None:
        return (
            "the tree was NOT preserved on a run-scoped ref (no run id was parsed from "
            f"the launch output, so no such ref can be named), {_FALL_BACK_TO_POINTER}"
        )
    if _NO_RUN_ID_SENTINEL in text:
        return (
            "the tree was NOT preserved on a run-scoped ref (the terminal reported that "
            f"no run id reached it, so there was no ref to push), {_FALL_BACK_TO_POINTER}"
        )
    if _PUSH_FAILED_SENTINEL in text:
        return (
            "the tree was NOT preserved on a run-scoped ref (the terminal reported that "
            f"its preservation push failed), {_FALL_BACK_TO_POINTER}"
        )
    ref = f"refs/heads/needs-human/{run_id}"
    return f"the tree was preserved on {ref} ({_PRESERVED_POINTER})"


def _decision(*, work_item_id: str) -> str:
    """Where the decision lives, which is the ledger and never a live run."""
    return (
        "no run is waiting — the decision lives in the ledger: answer with "
        f"`resolve-blocked:{work_item_id}:ready` (re-dispatch, seeding rework from "
        "the preserved ref or from scratch) or leave the item blocked"
    )
